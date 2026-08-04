import hashlib

from backend.models.experiment import Condition, Experiment
from backend.models.run import Prompt, Run
from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from backend.services.assessment_version_service import persist_original_version
from backend.services.docx_authoring_pipeline import DocxAuthoringPipeline, PipelineResult
from backend.services.docx_authoring_provider import AuthoringResult
from backend.services.docx_sandbox_client import SandboxExecutionResult
from backend.services.docx_verification import VerificationIssue, VerificationReport
from backend.services.llm_client import LLMResult


def test_pipeline_result_keeps_structured_terminal_failure_evidence():
    report = VerificationReport(False, (VerificationIssue("semantic_mismatch"),))
    result = PipelineResult.rewrite_failed(report)
    assert not result.succeeded
    assert result.status == "rewrite_failed"
    assert result.report.issues[0].code == "semantic_mismatch"


def test_pipeline_classifies_security_failure_without_repair():
    assert DocxAuthoringPipeline._execution_issue_code("policy_rejected") == "policy_rejected"


def saved_run(db):
    experiment = Experiment(course="MSE", topic="Phases", learning_objectives=["Analyze"], assessment_type="mcq", difficulty="medium", number_of_questions=1)
    condition = Condition(experiment=experiment, prompt_structure="openai", factor_inputs={}, condition_label="test")
    run = Run(experiment=experiment, condition=condition, run_number=1, model_settings={}, execution_config={})
    db.add(run); db.flush()
    run.prompt = Prompt(actual_prompt="Actual", actual_prompt_hash="a" * 64, prompt_structure="openai", structure_system_prompt="system", structure_input="input", structure_prompt_version="v1", actual_prompt_generator_version="v1", generation_context="", execution_system_prompt="", execution_user_message="", execution_schema_version="1", generation_envelope_hash="b" * 64)
    db.commit()
    persist_original_version(db, run=run, manifest={"questions": [{"id": "source-1", "body": "Original"}]})
    return run


class Provider:
    def __init__(self): self.calls = []
    def author_program(self, grounding, *, attempt_number, repair_context=None):
        self.calls.append((attempt_number, repair_context))
        envelope = DocxProgramEnvelope(schema_version="docx-program-envelope/1", language="python", entrypoint="program.py", program=f"# attempt {attempt_number}", expected_outputs=["assessment.docx", "assessment_manifest.json"], grounding_sha256=grounding.sha256, generation_notes="")
        return AuthoringResult(envelope, LLMResult("{}", f"response-{attempt_number}", "gemini-3.5-flash-lite", "v1", "STOP"), 1, "c" * 64)


class Sandbox:
    def execute(self, **kwargs):
        content = b"docx"
        return SandboxExecutionResult(kwargs["job_id"], "succeeded", content, {"questions": [{"body": "Rewrite"}]}, hashlib.sha256(content).hexdigest(), "d" * 64, "sha256:" + "e" * 64, {}, ())


class ValidPackage:
    def verify(self, value): return VerificationReport(True, (), hashlib.sha256(value).hexdigest(), tool_versions={"package": "1"})


class ValidManifest:
    def verify(self, value, manifest, grounding): return VerificationReport(True, (), hashlib.sha256(value).hexdigest(), "d" * 64, tool_versions={"manifest": "1"})


class ValidRender:
    def verify(self, value): return VerificationReport(True, (), hashlib.sha256(value).hexdigest(), rendered_page_count=1, tool_versions={"render": "1"})


def test_pipeline_canonicalizes_only_after_all_gates_pass(test_db):
    run = saved_run(test_db)
    provider = Provider()
    result = DocxAuthoringPipeline(test_db, provider=provider, sandbox=Sandbox(), package_verifier=ValidPackage(), manifest_verifier=ValidManifest(), render_verifier=ValidRender()).run(run.id)
    test_db.refresh(run)
    assert result.succeeded
    assert run.canonical_assessment.version == 2
    assert run.document_artifact.content == b"docx"
    assert [usage.stage for usage in run.model_call_usages] == ["docx_code_generation"]
