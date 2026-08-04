from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile
from docx_sandbox.config import SandboxSettings
from docx_sandbox.contracts import ExecuteRequest, ResultStatus, sha256_program
from docx_sandbox.runner import JobResult, JobSpec, SandboxRunner

PROGRAM = "from docx import Document\nDocument().save('/output/assessment.docx')\nopen('/output/assessment_manifest.json','w').write('{}')"
DOCX = BytesIO()
with ZipFile(DOCX, "w") as archive: archive.writestr("[Content_Types].xml", "<Types/>")
class FakeEngine:
    def __init__(self, result): self.result, self.spec = result, None
    def run_job(self, spec, program): self.spec = spec; return self.result

def req(): return ExecuteRequest(job_id=uuid4(), cycle_number=1, attempt_number=1, envelope_version="docx-program-envelope/1", program=PROGRAM, program_sha256=sha256_program(PROGRAM), grounding_sha256="a"*64)
def settings(): return SandboxSettings(job_image_digest="sha256:"+"a"*64)

def test_runner_launches_with_hard_limits_and_returns_artifact():
    engine = FakeEngine(JobResult(ResultStatus.succeeded, 0, outputs={"assessment.docx": DOCX.getvalue(), "assessment_manifest.json": b"{}"}))
    response = SandboxRunner(settings(), engine).execute(req())
    assert response.status is ResultStatus.succeeded
    assert engine.spec == JobSpec("sha256:"+"a"*64, memory_bytes=512*1024*1024, nano_cpus=1_000_000_000, pids_limit=64, timeout_seconds=45)
    assert response.evidence.output_sizes["assessment.docx"] == len(DOCX.getvalue())

def test_runner_rejects_extra_outputs():
    engine = FakeEngine(JobResult(ResultStatus.succeeded, 0, outputs={"assessment.docx": DOCX.getvalue(), "assessment_manifest.json": b"{}", "secret.txt": b"x"}))
    assert SandboxRunner(settings(), engine).execute(req()).status is ResultStatus.output_rejected

def test_runner_preserves_timeout_evidence():
    engine = FakeEngine(JobResult(ResultStatus.timed_out, termination_reason="timeout"))
    result = SandboxRunner(settings(), engine).execute(req())
    assert result.status is ResultStatus.timed_out and result.evidence.termination_reason == "timeout"
