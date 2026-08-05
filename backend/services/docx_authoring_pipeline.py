from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.docx_authoring import DocxAuthoringAttempt
from backend.models.experiment import utc_now
from backend.models.run import Run
from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from backend.services.assessment_version_service import persist_rewrite_and_canonicalize
from backend.services.docx_authoring_provider import RepairContext
from backend.services.document_artifact import generated_docx_artifact
from backend.services.docx_grounding import build_docx_grounding
from backend.services.docx_manifest_verifier import DocxManifestVerifier
from backend.services.docx_package_verifier import DocxPackageVerifier
from backend.services.docx_render_verifier import DocxRenderVerifier
from backend.services.docx_repair_policy import DocxRepairPolicy
from backend.services.docx_sandbox_client import (
    DocxSandboxClient,
    SandboxTransportError,
    stable_job_id,
)
from backend.services.docx_verification import VerificationIssue, VerificationReport
from backend.services.gemini_docx_authoring import AuthoringEnvelopeError, GeminiDocxAuthoringProvider
from backend.services.reference_pdfs import ProviderFileAttachment
from backend.services.usage_tracking import record_model_call


@dataclass(frozen=True)
class PipelineResult:
    succeeded: bool
    status: str
    report: VerificationReport
    assessment_id: int | None = None

    @classmethod
    def rewrite_failed(cls, report: VerificationReport):
        return cls(False, "rewrite_failed", report)


class DocxAuthoringPipeline:
    def __init__(
        self,
        db: Session,
        *,
        provider=None,
        sandbox=None,
        package_verifier=None,
        manifest_verifier=None,
        render_verifier=None,
        repair_policy=None,
        progress: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.provider = provider or GeminiDocxAuthoringProvider()
        self.sandbox = sandbox or DocxSandboxClient()
        self.package_verifier = package_verifier or DocxPackageVerifier()
        self.manifest_verifier = manifest_verifier or DocxManifestVerifier()
        self.render_verifier = render_verifier or DocxRenderVerifier()
        self.repair_policy = repair_policy or DocxRepairPolicy()
        self.progress = progress or (lambda _stage: None)

    def run(
        self,
        run_id: int,
        *,
        attachments: Iterable[ProviderFileAttachment] = (),
    ) -> PipelineResult:
        run = self.db.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        grounding = build_docx_grounding(run, attachments=attachments)
        resumable = self._resumable_attempt(run_id)
        cycle = resumable.cycle_number if resumable is not None else self._next_cycle(run_id)
        repair_context = None
        previous_program = resumable.program_text if resumable is not None else ""
        first_attempt = resumable.attempt_number if resumable is not None else 1
        for attempt_number in range(first_attempt, 3):
            self.progress("docx_repairing" if attempt_number == 2 else "docx_authoring")
            stage = "docx_code_repair" if attempt_number == 2 else "docx_code_generation"
            if (
                resumable is not None
                and attempt_number == resumable.attempt_number
                and resumable.status != "requested"
            ):
                attempt = resumable
                envelope = DocxProgramEnvelope.model_validate(attempt.envelope)
                if attempt.grounding_hash != grounding.sha256:
                    raise ValueError("persisted authoring attempt grounding hash mismatch")
                resumable = None
            else:
                try:
                    authored = self.provider.author_program(
                        grounding,
                        attempt_number=attempt_number,
                        repair_context=repair_context,
                    )
                except AuthoringEnvelopeError as exc:
                    report = VerificationReport(
                        False,
                        (VerificationIssue("program_schema_invalid", evidence=str(exc)),),
                    )
                    if attempt_number == 2 or not self.repair_policy.may_repair(report):
                        return PipelineResult.rewrite_failed(report)
                    repair_context = RepairContext.from_report(report)
                    continue
                usage = record_model_call(
                    self.db,
                    run=run,
                    call_id=str(uuid.uuid4()),
                    stage=stage,
                    attempt=attempt_number,
                    result=authored.provider_result,
                )
                envelope = authored.envelope
                previous_program = envelope.program
                if resumable is not None and resumable.status == "requested":
                    attempt = resumable
                    attempt.status = "generated"
                    attempt.provider = "openai"
                    attempt.model = authored.provider_result.model_name
                    attempt.model_version = authored.provider_result.model_version
                    attempt.provider_request_id = authored.provider_result.provider_request_id
                    attempt.model_call_usage_id = usage.id
                    attempt.prompt_hash = authored.prompt_sha256
                    attempt.program_text = envelope.program
                    attempt.envelope = envelope.model_dump()
                    resumable = None
                else:
                    attempt = DocxAuthoringAttempt(
                        run_id=run.id,
                        source_assessment_id=grounding.payload["original_assessment"]["assessment_id"],
                        cycle_number=cycle,
                        attempt_number=attempt_number,
                        status="generated",
                        provider="openai",
                        model=authored.provider_result.model_name,
                        model_version=authored.provider_result.model_version,
                        provider_request_id=authored.provider_result.provider_request_id,
                        model_call_usage_id=usage.id,
                        prompt_hash=authored.prompt_sha256,
                        grounding_hash=grounding.sha256,
                        idempotency_key=f"{run.id}:{cycle}" if attempt_number == 1 else None,
                        program_text=envelope.program,
                        envelope=envelope.model_dump(),
                        execution_report={},
                        validation_report={},
                    )
                    self.db.add(attempt)
                self.db.commit()
            self.progress("docx_executing")
            attempt.status = "executing"
            self.db.commit()
            try:
                executed = self.sandbox.execute(
                    job_id=stable_job_id(run.id, cycle, attempt_number),
                    cycle_number=cycle,
                    attempt_number=attempt_number,
                    envelope=envelope,
                    grounding_sha256=grounding.sha256,
                )
            except SandboxTransportError:
                # Keep the generated program and stable job ID resumable. The sandbox
                # endpoint is replay-safe, so a later worker delivery cannot double-run.
                attempt.status = "executing"
                self.db.commit()
                raise
            attempt.sandbox_image_digest = executed.image_digest.removeprefix("sha256:")
            attempt.execution_report = {
                "job_id": executed.job_id,
                "status": executed.status,
                "docx_sha256": executed.docx_sha256,
                "manifest_sha256": executed.manifest_sha256,
                "evidence": executed.evidence,
                "issues": list(executed.issues),
            }
            if not executed.succeeded or executed.docx_bytes is None or executed.manifest is None:
                code = self._execution_issue_code(executed.status, executed.issues)
                report = VerificationReport(
                    False,
                    (VerificationIssue(code, repairable=code not in {"policy_rejected"}, evidence="; ".join(executed.issues)[:1000]),),
                    execution=attempt.execution_report,
                )
            else:
                self.progress("docx_validating")
                attempt.status = "validating"
                self.db.commit()
                report = self._verify(executed.docx_bytes, executed.manifest, grounding, attempt.execution_report)
            attempt.validation_report = report.as_dict()
            if report.valid:
                artifact = generated_docx_artifact(
                    run_id=run.id, content=executed.docx_bytes
                )
                try:
                    rewrite = persist_rewrite_and_canonicalize(
                        self.db,
                        run=run,
                        manifest=executed.manifest,
                        artifact=artifact,
                        schema_version="rewritten-assessment/1",
                    )
                except Exception as exc:
                    report = VerificationReport(
                        False,
                        (VerificationIssue("persistence_failed", repairable=False, evidence=type(exc).__name__),),
                        package_sha256=report.package_sha256,
                        manifest_sha256=report.manifest_sha256,
                        rendered_page_count=report.rendered_page_count,
                        tool_versions=report.tool_versions,
                        execution=report.execution,
                    )
                    attempt.status = "failed"
                    attempt.failure_category = "persistence_failed"
                    attempt.repairable = False
                    attempt.validation_report = report.as_dict()
                    attempt.completed_at = utc_now()
                    self.db.add(attempt)
                    self.db.commit()
                    return PipelineResult.rewrite_failed(report)
                attempt.status = "succeeded"
                attempt.completed_at = utc_now()
                self.db.add(attempt)
                self.db.commit()
                return PipelineResult(True, "complete", report, rewrite.id)
            attempt.status = "failed"
            attempt.failure_category = report.issues[0].code if report.issues else "verification_failed"
            attempt.repairable = self.repair_policy.may_repair(report)
            attempt.completed_at = utc_now()
            self.db.commit()
            if attempt_number == 2 or not attempt.repairable:
                return PipelineResult.rewrite_failed(report)
            repair_context = RepairContext.from_report(report, previous_program)
        raise AssertionError("bounded authoring loop exhausted")

    def _next_cycle(self, run_id: int) -> int:
        highest = self.db.scalar(
            select(func.max(DocxAuthoringAttempt.cycle_number)).where(
                DocxAuthoringAttempt.run_id == run_id
            )
        )
        return (highest or 0) + 1

    def _resumable_attempt(self, run_id: int):
        return self.db.scalar(
            select(DocxAuthoringAttempt)
            .where(
                DocxAuthoringAttempt.run_id == run_id,
                DocxAuthoringAttempt.status.in_(("requested", "generated", "executing", "validating")),
            )
            .order_by(
                DocxAuthoringAttempt.cycle_number.desc(),
                DocxAuthoringAttempt.attempt_number.desc(),
            )
            .limit(1)
        )

    def _verify(self, docx_bytes, manifest, grounding, execution) -> VerificationReport:
        package = self.package_verifier.verify(docx_bytes)
        if not package.valid:
            return VerificationReport(False, package.issues, package.package_sha256, execution=execution, tool_versions=package.tool_versions)
        semantic = self.manifest_verifier.verify(docx_bytes, manifest, grounding)
        if not semantic.valid:
            return VerificationReport(False, semantic.issues, semantic.package_sha256, semantic.manifest_sha256, tool_versions=semantic.tool_versions, execution=execution)
        rendered = self.render_verifier.verify(docx_bytes)
        issues = semantic.issues + rendered.issues
        return VerificationReport(
            valid=semantic.valid and rendered.valid,
            issues=issues,
            package_sha256=semantic.package_sha256,
            manifest_sha256=semantic.manifest_sha256,
            rendered_page_count=rendered.rendered_page_count,
            tool_versions={**package.tool_versions, **semantic.tool_versions, **rendered.tool_versions},
            execution=execution,
            render_duration_ms=rendered.render_duration_ms,
        )

    @staticmethod
    def _execution_issue_code(status: str, issues=()) -> str:
        if status == "policy_rejected" and any(
            str(issue).startswith("syntax_error:") for issue in issues
        ):
            return "python_syntax_error"
        return {
            "policy_rejected": "policy_rejected",
            "timed_out": "timed_out",
            "resource_exhausted": "resource_exhausted",
            "execution_failed": "execution_failed",
            "output_rejected": "required_output_missing",
        }.get(status, "execution_failed")
