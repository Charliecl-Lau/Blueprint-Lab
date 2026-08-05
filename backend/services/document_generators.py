"""Backend-specific document generator adapters with one result contract."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import DocxToolAction, DocxToolIteration, DocxToolSession, Run
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
    def generate(self, *, db: Session, run: Run, attachments=(), progress=lambda _: None) -> DocumentGenerationResult:
        source = next((item for item in run.assessment_versions if item.version == 1), None)
        if source is None or source.parsed_json is None:
            return DocumentGenerationResult(False, False, ("source_assessment_missing",))
        catalog = DocxContentCatalog.from_assessment(source.parsed_json)
        cycle = (db.scalar(select(func.max(DocxToolSession.cycle_number)).where(DocxToolSession.run_id == run.id)) or 0) + 1
        prompt_root = Path(__file__).resolve().parents[1] / "prompts"
        contract = (prompt_root / "docx_tool_design_system.md").read_bytes() + (prompt_root / "docx_tool_visual_review.md").read_bytes()
        session = DocxToolSession(
            run_id=run.id, source_assessment_id=source.id, cycle_number=cycle,
            provider="openai", model=DOCX_TOOL_MODEL, status="pending",
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
        artifact = generated_docx_artifact(run_id=run.id, content=result.compiled.docx_bytes)
        persist_rewrite_and_canonicalize(db, run=run, manifest=result.compiled.assessment_json, artifact=artifact, schema_version=source.schema_version)
        return DocumentGenerationResult(True, True)


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
    ) -> DocumentGenerationResult:
        source = next(
            (item for item in run.assessment_versions if item.version == 1),
            None,
        )
        if source is None or source.parsed_json is None:
            return DocumentGenerationResult(
                False, False, ("source_assessment_missing",)
            )
        progress("docx_authoring")
        try:
            provider = self.provider or LunaDirectDocxProvider()
            generated = provider.generate(source.parsed_json, run_id=run.id)
        except LunaDocxGenerationError as exc:
            return DocumentGenerationResult(False, False, (exc.code,))
        record_model_call(
            db,
            run=run,
            call_id=str(uuid.uuid4()),
            stage="docx_direct_generation",
            attempt=1,
            result=generated.provider_result,
        )
        progress("docx_validating")
        report = self.verifier.verify(generated.content, source.parsed_json)
        if not report.valid:
            return DocumentGenerationResult(
                False,
                False,
                tuple(dict.fromkeys(issue.code for issue in report.issues)),
            )
        artifact = generated_docx_artifact(run_id=run.id, content=generated.content)
        persist_rewrite_and_canonicalize(
            db,
            run=run,
            manifest=source.parsed_json,
            artifact=artifact,
            schema_version=source.schema_version,
        )
        return DocumentGenerationResult(True, True)


class DocumentGeneratorRegistry:
    def __init__(self):
        self._generators = {
            "luna_direct": LunaDirectDocumentGenerator(),
            "legacy": LegacyDocumentGenerator(),
            "self_hosted_code": SelfHostedCodeDocumentGenerator(),
            "agentic_tools": AgenticToolDocumentGenerator(),
        }
    def get(self, name): return self._generators[name]


document_generator_registry = DocumentGeneratorRegistry()
