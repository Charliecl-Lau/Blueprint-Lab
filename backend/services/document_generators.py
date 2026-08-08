"""Backend-specific document generator adapters with one result contract."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import (
    DocxToolAction, DocxToolIteration, DocxToolSession,
    LunaDocxAttempt, LunaDocxSession, Run,
)
from backend.models.experiment import utc_now
from backend.services.agentic_docx_pipeline import AgenticDocxPipeline, AgenticPipelineResult
from backend.services.assessment_version_service import persist_rewrite_and_canonicalize
from backend.services.document_artifact import generated_docx_artifact, save_assessment_artifact
from backend.services.docx_content_catalog import DocxContentCatalog
from backend.services.docx_visual_renderer import DocxVisualRenderer
from backend.services.docx_tool_workspace import DocxWorkspace
from backend.services.gemini_docx_tool_agent import DOCX_TOOL_MODEL, GeminiDocxToolAgent
from backend.services.luna_direct_docx_provider import (
    LunaDirectDocxProvider,
    LunaDocxGenerationError,
)
from backend.services.luna_direct_docx_verifier import LunaDirectDocxVerifier
from backend.services.usage_tracking import record_model_call


@dataclass(frozen=True)
class DocumentGenerationResult:
    succeeded: bool
    canonicalized: bool
    safe_issue_codes: tuple[str, ...] = ()
    artifact_content: bytes | None = None


def auto_download_docx(*, run_id: int, provider: str, content: bytes) -> Path:
    """Atomically save a provider comparison artifact to the configured folder."""
    destination = Path(settings.docx_auto_download_dir)
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / f"blueprint-lab-run-{run_id}-{provider}.docx"
    temporary_path = destination / f".{final_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary_path.write_bytes(content)
        os.replace(temporary_path, final_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return final_path


class LegacyDocumentGenerator:
    def generate(self, *, db: Session, run: Run, attachments=(), progress=lambda _: None) -> DocumentGenerationResult:
        progress("documenting"); save_assessment_artifact(db, run); db.commit()
        return DocumentGenerationResult(True, True)


class SelfHostedCodeDocumentGenerator:
    def generate(self, *, db: Session, run: Run, attachments=(), progress=lambda _: None) -> DocumentGenerationResult:
        from backend.services.docx_authoring_pipeline import DocxAuthoringPipeline
        result = DocxAuthoringPipeline(db, progress=progress).run(run.id, attachments=attachments)
        codes = tuple(issue.code for issue in result.report.issues)
        return DocumentGenerationResult(result.succeeded, result.succeeded, codes)


class AgenticToolDocumentGenerator:
    def generate(self, *, db: Session, run: Run, attachments=(), progress=lambda _: None, persist_artifact: bool = True) -> DocumentGenerationResult:
        source = next((item for item in run.assessment_versions if item.version == 1), None)
        if source is None or source.parsed_json is None:
            return DocumentGenerationResult(False, False, ("source_assessment_missing",))
        catalog = DocxContentCatalog.from_assessment(source.parsed_json)
        cycle = (db.scalar(select(func.max(DocxToolSession.cycle_number)).where(DocxToolSession.run_id == run.id)) or 0) + 1
        prompt_root = Path(__file__).resolve().parents[1] / "prompts"
        contract = (prompt_root / "docx_tool_design_system.md").read_bytes() + (prompt_root / "docx_tool_visual_review.md").read_bytes()
        session = DocxToolSession(
            run_id=run.id, source_assessment_id=source.id, cycle_number=cycle,
            provider="google", model=DOCX_TOOL_MODEL, status="pending",
            content_catalog_hash=catalog.sha256, design_contract_hash=hashlib.sha256(contract).hexdigest(),
            workspace_revision=0, maximum_revisions=settings.docx_tool_max_revisions,
            idempotency_key=f"run-{run.id}-agentic-cycle-{cycle}",
        )
        session.initial_workspace_hash = DocxWorkspace.create(catalog).sha256
        db.add(session); db.commit(); db.refresh(session)
        iterations = {}

        def on_model(stage, attempt, turn_result):
            kind = "design" if stage == "docx_tool_design" else "visual_revision"
            number = 0 if kind == "design" else attempt
            iteration = iterations.get(number)
            if iteration is None:
                iteration = DocxToolIteration(session_id=session.id, iteration_number=number, kind=kind, input_workspace_hash=session.final_workspace_hash or session.initial_workspace_hash)
                db.add(iteration); db.flush(); iterations[number] = iteration
            usage = record_model_call(db, run=run, call_id=str(uuid.uuid4()), stage=stage, attempt=attempt, result=turn_result.provider_result)
            iteration.model_call_usage_id = usage.id
            db.commit()

        def on_actions(number, kind, calls, execution):
            iteration = iterations.get(number)
            if iteration is None:
                iteration = DocxToolIteration(session_id=session.id, iteration_number=number, kind=kind, input_workspace_hash=session.final_workspace_hash or session.initial_workspace_hash)
                db.add(iteration); db.flush(); iterations[number] = iteration
            for sequence, (call, action) in enumerate(zip(calls, execution.actions)):
                db.add(DocxToolAction(session_id=session.id, iteration_id=iteration.id, sequence_number=sequence, operation_id=call.operation_id, tool_name=call.tool, validated_arguments=call.arguments.model_dump(exclude_none=True), status="succeeded", before_workspace_hash=action.before_hash, after_workspace_hash=action.after_hash, duration_ms=0))
            iteration.output_workspace_hash = execution.workspace_hash
            session.workspace_revision = execution.workspace_revision; session.final_workspace_hash = execution.workspace_hash
            db.commit()

        def on_render(number, compiled, rendered):
            iteration = iterations.get(number)
            if iteration is None:
                kind = "design" if number == 0 else "visual_revision"
                iteration = DocxToolIteration(session_id=session.id, iteration_number=number, kind=kind, input_workspace_hash=session.final_workspace_hash or session.initial_workspace_hash)
                db.add(iteration); db.flush(); iterations[number] = iteration
            iteration.draft_docx_hash = compiled.docx_sha256
            iteration.draft_pdf_hash = rendered.pdf_sha256
            iteration.page_image_metadata = [page.public_metadata() for page in rendered.pages]
            iteration.validator_report = {"findings": [finding.__dict__ for finding in rendered.findings], "valid": not any(f.severity == "error" for f in rendered.findings)}
            db.commit()

        def session_progress(stage):
            session.status = {"docx_authoring": "designing", "docx_executing": "executing", "docx_validating": "validating", "docx_repairing": "reviewing"}.get(stage, session.status)
            db.commit(); progress(stage)

        renderer = DocxVisualRenderer(
            libreoffice_command=settings.docx_render_command,
            timeout_seconds=settings.docx_render_timeout_seconds,
            max_pages=settings.docx_tool_max_review_pages,
            max_total_bytes=settings.docx_tool_max_review_image_bytes,
        )
        session.status = "designing"; db.commit()
        result: AgenticPipelineResult = AgenticDocxPipeline(
            agent=GeminiDocxToolAgent(max_operations=settings.docx_tool_max_operations_per_turn, max_pages=settings.docx_tool_max_review_pages),
            renderer=renderer, maximum_revisions=settings.docx_tool_max_revisions,
            maximum_total_seconds=settings.docx_tool_max_total_seconds,
            progress=session_progress, model_turn=on_model, action_batch=on_actions, rendered_draft=on_render,
        ).run(source.parsed_json, session_id=session.id)
        session.final_decision = result.decision
        session.status = "succeeded" if result.succeeded else "failed"
        session.workspace_revision = result.evidence.workspace_revision
        session.final_workspace_hash = result.evidence.workspace_hash
        session.completed_at = utc_now()
        for number, iteration in iterations.items():
            iteration.review_decision = result.evidence.review_decisions[number - 1] if number > 0 and number <= len(result.evidence.review_decisions) else None
            if not iteration.page_image_metadata:
                iteration.page_image_metadata = []
        if not result.succeeded or result.compiled is None:
            db.commit(); return DocumentGenerationResult(False, False, result.safe_issue_codes)
        content = result.compiled.docx_bytes
        if persist_artifact:
            artifact = generated_docx_artifact(run_id=run.id, content=content)
            persist_rewrite_and_canonicalize(db, run=run, manifest=result.compiled.assessment_json, artifact=artifact, schema_version=source.schema_version)
        return DocumentGenerationResult(True, persist_artifact, artifact_content=content)


class LunaDirectDocumentGenerator:
    def __init__(self, provider=None, verifier=None):
        self.provider = provider
        self.verifier = verifier or LunaDirectDocxVerifier()

    def generate(
        self,
        *,
        db: Session,
        run: Run,
        attachments=(),
        progress=lambda _: None,
        persist_artifact: bool = True,
    ) -> DocumentGenerationResult:
        source = next(
            (item for item in run.assessment_versions if item.version == 1),
            None,
        )
        if source is None or source.parsed_json is None:
            return DocumentGenerationResult(
                False, False, ("source_assessment_missing",)
            )
        provider = self.provider or LunaDirectDocxProvider()
        feedback: tuple[str, ...] = ()
        report = None
        generated = None
        cycle_number = (
            db.scalar(
                select(func.max(LunaDocxSession.cycle_number)).where(
                    LunaDocxSession.run_id == run.id
                )
            ) or 0
        ) + 1
        luna_session = LunaDocxSession(
            run_id=run.id,
            source_assessment_id=source.id,
            cycle_number=cycle_number,
            status="creating",
            maximum_repairs=settings.docx_tool_max_revisions,
            repair_count=0,
            attempt_count=0,
            final_issue_codes=[],
        )
        db.add(luna_session)
        db.commit()
        db.refresh(luna_session)
        container_session = None
        # ``docx_tool_max_revisions`` counts repairs after the initial authoring
        # attempt, so two revisions means up to three provider calls.
        maximum_attempts = 1 + settings.docx_tool_max_revisions
        try:
            if getattr(provider, "supports_reusable_session", False) is True:
                container_session = provider.create_session(
                    source.parsed_json, run_id=run.id
                )
                luna_session.container_id = container_session.container_id
                db.commit()
            for attempt in range(1, maximum_attempts + 1):
                progress("docx_authoring" if attempt == 1 else "docx_repairing")
                luna_session.status = "authoring" if attempt == 1 else "repairing"
                luna_session.attempt_count = attempt
                luna_session.repair_count = attempt - 1
                attempt_record = LunaDocxAttempt(
                    session_id=luna_session.id,
                    attempt_number=attempt,
                    kind="initial" if attempt == 1 else "repair",
                    status="requested",
                    input_artifact_sha256=(
                        luna_session.attempts[-1].output_artifact_sha256
                        if luna_session.attempts else None
                    ),
                    issue_codes=[], validation_report={}, repair_feedback={},
                )
                db.add(attempt_record)
                db.commit()
                generate_kwargs = {
                    "run_id": run.id,
                    "verification_feedback": feedback,
                }
                if container_session is not None:
                    generate_kwargs["session"] = container_session
                try:
                    generated = provider.generate(source.parsed_json, **generate_kwargs)
                except LunaDocxGenerationError as exc:
                    attempt_record.status = "failed"
                    attempt_record.provider_failure_code = exc.code
                    attempt_record.issue_codes = [exc.code]
                    attempt_record.completed_at = utc_now()
                    luna_session.status = "failed"
                    luna_session.outcome = "failed"
                    luna_session.failure_category = exc.code
                    luna_session.final_issue_codes = [exc.code]
                    luna_session.completed_at = utc_now()
                    db.commit()
                    return DocumentGenerationResult(False, False, (exc.code,))
                attempt_record.status = "generated"
                attempt_record.provider_response_id = generated.provider_result.provider_request_id
                attempt_record.prompt_hash = generated.prompt_sha256
                attempt_record.output_artifact_sha256 = hashlib.sha256(generated.content).hexdigest()
                usage = record_model_call(
                    db,
                    run=run,
                    call_id=str(uuid.uuid4()),
                    stage="docx_direct_generation",
                    attempt=attempt,
                    result=generated.provider_result,
                )
                if not any(
                    item.model_call_usage_id == usage.id
                    for item in luna_session.attempts
                    if item.id != attempt_record.id
                ):
                    attempt_record.model_call_usage_id = usage.id
                progress("docx_validating")
                luna_session.status = "validating"
                attempt_record.status = "validating"
                report = self.verifier.verify(generated.content, source.parsed_json)
                attempt_record.validation_report = report.as_dict()
                attempt_record.issue_codes = list(dict.fromkeys(i.code for i in report.issues))
                attempt_record.status = "succeeded" if report.valid else "failed"
                attempt_record.completed_at = utc_now()
                db.commit()
                if report.valid:
                    break
                feedback_payload = {
                    "issues": [issue.as_dict() for issue in report.issues],
                    "artifact_sha256": attempt_record.output_artifact_sha256,
                }
                attempt_record.repair_feedback = feedback_payload
                db.commit()
                if any(not issue.repairable for issue in report.issues):
                    break
                feedback = tuple(
                    f"{issue.code}: {issue.evidence or 'no additional evidence'}"
                    for issue in report.issues
                )
            if report is None or generated is None or not report.valid:
                codes = tuple(dict.fromkeys(issue.code for issue in report.issues)) if report else ("docx_generation_failed",)
                luna_session.status = "failed"
                luna_session.outcome = "failed"
                luna_session.failure_category = codes[0] if codes else "verification_failed"
                luna_session.final_issue_codes = list(codes)
                luna_session.completed_at = utc_now()
                db.commit()
                return DocumentGenerationResult(False, False, codes)
            if persist_artifact:
                artifact = generated_docx_artifact(run_id=run.id, content=generated.content)
                persist_rewrite_and_canonicalize(
                    db,
                    run=run,
                    manifest=source.parsed_json,
                    artifact=artifact,
                    schema_version=source.schema_version,
                )
            luna_session.status = "succeeded"
            luna_session.outcome = "succeeded"
            luna_session.final_issue_codes = []
            luna_session.final_artifact_sha256 = hashlib.sha256(generated.content).hexdigest()
            luna_session.completed_at = utc_now()
            db.commit()
            return DocumentGenerationResult(
                True,
                persist_artifact,
                artifact_content=generated.content,
            )
        except LunaDocxGenerationError as exc:
            luna_session.status = "failed"
            luna_session.outcome = "failed"
            luna_session.failure_category = exc.code
            luna_session.final_issue_codes = [exc.code]
            luna_session.completed_at = utc_now()
            db.commit()
            return DocumentGenerationResult(False, False, (exc.code,))
        finally:
            if container_session is not None:
                if not provider.close_session(container_session):
                    luna_session.cleanup_error_code = "container_cleanup_failed"
                    db.commit()


class GeminiLunaPairDocumentGenerator:
    """Generate two DOCX files from assessment version 1 for direct comparison."""

    def __init__(self, gemini=None, luna=None, downloader=auto_download_docx):
        self.gemini = gemini or AgenticToolDocumentGenerator()
        self.luna = luna or LunaDirectDocumentGenerator()
        self.downloader = downloader

    def generate(
        self,
        *,
        db: Session,
        run: Run,
        attachments=(),
        progress=lambda _: None,
    ) -> DocumentGenerationResult:
        issue_codes: list[str] = []
        gemini_result = self.gemini.generate(
            db=db,
            run=run,
            attachments=attachments,
            progress=progress,
            persist_artifact=False,
        )
        if gemini_result.succeeded and gemini_result.artifact_content is not None:
            self.downloader(
                run_id=run.id,
                provider="gemini",
                content=gemini_result.artifact_content,
            )
        else:
            issue_codes.extend(gemini_result.safe_issue_codes or ("gemini_docx_failed",))

        luna_result = self.luna.generate(
            db=db,
            run=run,
            attachments=attachments,
            progress=progress,
            persist_artifact=True,
        )
        if luna_result.succeeded and luna_result.artifact_content is not None:
            self.downloader(
                run_id=run.id,
                provider="luna",
                content=luna_result.artifact_content,
            )
        else:
            issue_codes.extend(luna_result.safe_issue_codes or ("luna_docx_failed",))

        return DocumentGenerationResult(
            succeeded=not issue_codes,
            canonicalized=luna_result.canonicalized,
            safe_issue_codes=tuple(dict.fromkeys(issue_codes)),
            artifact_content=luna_result.artifact_content,
        )


class DocumentGeneratorRegistry:
    def __init__(self):
        self._generators = {
            "gemini_luna_pair": GeminiLunaPairDocumentGenerator(),
            "luna_direct": LunaDirectDocumentGenerator(),
            "legacy": LegacyDocumentGenerator(),
            "self_hosted_code": SelfHostedCodeDocumentGenerator(),
            "agentic_tools": AgenticToolDocumentGenerator(),
        }
    def get(self, name): return self._generators[name]


document_generator_registry = DocumentGeneratorRegistry()
