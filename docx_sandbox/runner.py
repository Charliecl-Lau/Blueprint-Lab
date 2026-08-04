from __future__ import annotations
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol
from .config import SandboxSettings
from .contracts import ExecuteRequest, ExecuteResponse, ExecutionEvidence, ResultStatus


@dataclass(frozen=True)
class JobSpec:
    image_digest: str
    network_mode: str = "none"
    read_only_root: bool = True
    user: str = "65532:65532"
    memory_bytes: int = 512 * 1024 * 1024
    nano_cpus: int = 1_000_000_000
    pids_limit: int = 64
    timeout_seconds: int = 45
    cap_drop: tuple[str, ...] = ("ALL",)
    no_new_privileges: bool = True


@dataclass(frozen=True)
class JobResult:
    status: ResultStatus
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    termination_reason: Optional[str] = None
    outputs: Optional[Dict[str, bytes]] = None
    wall_time_ms: int = 0


class ContainerEngine(Protocol):
    def run_job(self, spec: JobSpec, program: str) -> JobResult: ...


class DockerEngine:
    def __init__(self, settings: SandboxSettings): self.settings = settings

    def run_job(self, spec: JobSpec, program: str) -> JobResult:
        root = Path(tempfile.mkdtemp(prefix="docx-sandbox-"))
        output = root / "output"; output.mkdir()
        job = root / "job"; job.mkdir()
        normalized = program.replace("\r\n", "\n").replace("\r", "\n")
        (job / "program.py").write_bytes(normalized.encode("utf-8"))
        name = "docx-sandbox-" + os.urandom(8).hex()
        args = ["docker", "run", "--name", name, "--network", spec.network_mode, "--read-only", "--user", spec.user,
                "--memory", str(spec.memory_bytes), "--cpus", str(spec.nano_cpus / 1_000_000_000), "--pids-limit", str(spec.pids_limit),
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "-v", f"{job}:/job:ro", "-v", f"{self.settings.assets_dir}:/assets:ro", "-v", f"{output}:/output:rw", f"{spec.image_digest}"]
        started = time.monotonic()
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=spec.timeout_seconds, check=False)
            status = ResultStatus.succeeded if proc.returncode == 0 else ResultStatus.execution_failed
            outputs = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
            return JobResult(status, proc.returncode, proc.stdout[-8192:], proc.stderr[-8192:], outputs=outputs, wall_time_ms=int((time.monotonic() - started) * 1000))
        except subprocess.TimeoutExpired as exc:
            return JobResult(ResultStatus.timed_out, None, str(exc.stdout or "")[-8192:], str(exc.stderr or "")[-8192:], "timeout", wall_time_ms=int((time.monotonic() - started) * 1000))
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            shutil.rmtree(root, ignore_errors=True)


class SandboxRunner:
    def __init__(self, settings: SandboxSettings, engine: ContainerEngine): self.settings, self.engine = settings, engine

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        spec = JobSpec(self.settings.job_image_digest, memory_bytes=self.settings.memory_bytes, nano_cpus=self.settings.nano_cpus, pids_limit=self.settings.pids_limit, timeout_seconds=self.settings.timeout_seconds)
        result = self.engine.run_job(spec, request.program)
        outputs = result.outputs or {}
        evidence = self._evidence(result, spec, outputs)
        issues = []
        if result.status is ResultStatus.succeeded:
            expected = {"assessment.docx", "assessment_manifest.json"}
            if set(outputs) != expected:
                result = JobResult(ResultStatus.output_rejected, result.exit_code, result.stdout, result.stderr, "invalid_output")
                evidence = self._evidence(result, spec, outputs)
                issues.append("exactly assessment.docx and assessment_manifest.json are required")
            elif any(len(v) > self.settings.max_output_bytes for v in outputs.values()):
                result = JobResult(ResultStatus.output_rejected, result.exit_code, result.stdout, result.stderr, "output_limit")
                evidence = self._evidence(result, spec, outputs); issues.append("output exceeds configured limit")
            else:
                try:
                    manifest = json.loads(outputs["assessment_manifest.json"])
                    if not isinstance(manifest, dict): raise ValueError("manifest must be an object")
                    with zipfile.ZipFile(io.BytesIO(outputs["assessment.docx"])) as archive:
                        names = set(archive.namelist())
                        if any(name.lower().endswith(("vbaProject.bin", ".exe", ".dll")) for name in names):
                            raise ValueError("macro or executable content")
                except (ValueError, json.JSONDecodeError):
                    result = JobResult(ResultStatus.output_rejected, result.exit_code, result.stdout, result.stderr, "malformed_manifest")
                    evidence = self._evidence(result, spec, outputs); issues.append("manifest is not valid JSON")
                except zipfile.BadZipFile:
                    result = JobResult(ResultStatus.output_rejected, result.exit_code, result.stdout, result.stderr, "invalid_docx")
                    evidence = self._evidence(result, spec, outputs); issues.append("assessment.docx is not a valid OOXML package")
        artifact = base64_encode(outputs.get("assessment.docx")) if result.status is ResultStatus.succeeded else None
        manifest = json.loads(outputs["assessment_manifest.json"]) if result.status is ResultStatus.succeeded else None
        manifest_artifact = base64_encode(outputs.get("assessment_manifest.json")) if result.status is ResultStatus.succeeded else None
        return ExecuteResponse(job_id=request.job_id, status=result.status, evidence=evidence, manifest_json=manifest, manifest_base64=manifest_artifact, artifact_base64=artifact, issues=issues)

    def _evidence(self, result, spec, outputs):
        return ExecutionEvidence(image_digest=spec.image_digest, exit_code=result.exit_code, wall_time_ms=result.wall_time_ms, termination_reason=result.termination_reason, output_names=sorted(outputs), output_sizes={k: len(v) for k,v in outputs.items()}, output_sha256={k: hashlib.sha256(v).hexdigest() for k,v in outputs.items()}, stdout=result.stdout[-8192:], stderr=result.stderr[-8192:])


def base64_encode(value: Optional[bytes]) -> Optional[str]:
    import base64
    return base64.b64encode(value).decode("ascii") if value is not None else None
