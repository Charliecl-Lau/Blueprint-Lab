# Plan 2: Self-Hosted DOCX Code Sandbox

**Goal:** Build the isolated service that accepts one validated DOCX Program Envelope, executes the LLM-authored Python in a disposable container, and returns a DOCX, manifest, logs, and execution evidence.

**Depends on:** Plan 1 data contracts. It can be implemented in parallel with Plan 1 after the attempt-record fields are agreed, but it must not be integrated with the worker until Plan 1 lands.

**Unblocks:** Plan 3.

**Architecture:** The worker calls a private HTTP service. That service performs a static policy preflight and launches a new, unprivileged job container for each request. The job has no network, no application credentials, a read-only root filesystem, fixed CPU/memory/time/PID limits, and one writable output directory. The runner returns bytes and evidence; it never persists application data.

**TDD rule:** Security policy and resource-boundary tests precede runner code. Tests may use a fake container engine; only the gated integration suite may require Docker.

## Proposed files

- Add `docx_sandbox/__init__.py`
- Add `docx_sandbox/config.py`
- Add `docx_sandbox/contracts.py`
- Add `docx_sandbox/preflight.py`
- Add `docx_sandbox/runner.py`
- Add `docx_sandbox/api.py`
- Add `docx_sandbox/job/entrypoint.py`
- Add `docx_sandbox/job/requirements.lock`
- Add `docx_sandbox/tests/test_contracts.py`
- Add `docx_sandbox/tests/test_preflight.py`
- Add `docx_sandbox/tests/test_runner.py`
- Add `docx_sandbox/tests/test_api.py`
- Add `docx_sandbox/tests/integration/test_job_container.py`
- Add `Dockerfile.docx-sandbox-service`
- Add `Dockerfile.docx-sandbox-job`
- Add `requirements.docx-sandbox.txt`

## Task 1: Define the internal execution contract

### 1. Write failing Pydantic contract tests

Valid requests contain:

- `job_id`, `cycle_number`, `attempt_number`, and exact program-envelope version;
- Python source as UTF-8 text;
- expected output names fixed to `assessment.docx` and `assessment_manifest.json`;
- expected grounding and program SHA-256 hashes;
- immutable job-image digest;
- no arbitrary command, environment variables, mounts, URLs, or paths.

Valid responses distinguish `succeeded`, `policy_rejected`, `timed_out`, `resource_exhausted`, `execution_failed`, and `output_rejected`.

Example request model:

```python
class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    cycle_number: int = Field(ge=1)
    attempt_number: Literal[1, 2]
    envelope_version: Literal["docx-program-envelope/1"]
    program: str = Field(min_length=1, max_length=750_000)
    program_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
```

The response returns the DOCX as a bounded binary body or base64 field only on the trusted private network. Prefer a multipart response if the existing infrastructure supports streaming; never place raw bytes in logs.

Run:

```powershell
pytest docx_sandbox/tests/test_contracts.py -q
```

### 2. Implement the models and deterministic hashing

Reject a request when the supplied program hash differs from the bytes that will be executed. Normalize line endings only before both hashing and execution, never between them.

### 3. Commit checkpoint

```text
Define the DOCX sandbox execution contract

This introduces a closed internal request and response schema so callers
cannot choose commands, mounts, environment variables, or output paths. Hashes
bind each execution to the exact generated program and grounding package.
```

## Task 2: Implement AST policy preflight

### 1. Write the hostile-program tests first

Use parameterized tests to reject:

- `subprocess`, `socket`, `requests`, `urllib`, `httpx`, `ftplib`, `paramiko`;
- `os.system`, `os.popen`, spawn/exec/fork calls, shell escapes;
- `ctypes`, `cffi`, dynamic imports, `eval`, `exec`, `compile`, `__import__`;
- reads outside the approved read-only asset directory;
- writes outside `/output`;
- symlink, hard-link, device, FIFO, and socket creation;
- environment and secret access;
- pickle and unsafe deserialization;
- attempts to mutate the mounted reference asset.

Also prove the valid fixture can import the pinned allowlist: `docx`, selected standard-library modules, and the project-supplied helper module.

Example policy skeleton:

```python
ALLOWED_IMPORT_ROOTS = {
    "docx", "json", "math", "statistics", "decimal", "fractions",
    "datetime", "textwrap", "re", "collections", "itertools",
}

FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "open", "__import__",
    "os.system", "os.popen",
}


def inspect_program(source: str) -> PolicyReport:
    tree = ast.parse(source, mode="exec")
    visitor = ProgramPolicyVisitor()
    visitor.visit(tree)
    return visitor.report()
```

Do not claim AST checks are a security boundary; they are an early rejection layer before container isolation.

Run:

```powershell
pytest docx_sandbox/tests/test_preflight.py -q
```

### 2. Implement and fuzz the preflight

Add syntax-depth and node-count limits to prevent pathological parsing. Return stable issue codes and source locations, but never echo more than a short sanitized excerpt.

Run:

```powershell
pytest docx_sandbox/tests/test_preflight.py -q
```

### 3. Commit checkpoint

```text
Reject unsafe DOCX programs before execution

This adds a deterministic AST preflight for forbidden imports, dynamic code,
process and network access, unsafe file operations, and pathological syntax.
It reduces attack surface before the disposable container boundary.
```

## Task 3: Build the disposable job image and entrypoint

### 1. Write failing entrypoint tests

The entrypoint must:

- read exactly `/job/program.py`;
- expose only `/assets` read-only and `/output` writable;
- execute with Python isolated mode;
- require exactly `assessment.docx` and `assessment_manifest.json`;
- reject extra files, symlinks, macros, executables, archives, and output exceeding configured byte limits;
- emit a small JSON execution report without document content.

Example success fixture:

```python
from docx import Document
import json

document = Document()
document.add_heading("Assessment Metadata", level=1)
document.save("/output/assessment.docx")
with open("/output/assessment_manifest.json", "w", encoding="utf-8") as handle:
    json.dump({"schema_version": "rewritten-assessment/1"}, handle)
```

The fixture uses `open` because runtime filesystem isolation constrains it; generated programs may instead be given a narrow project helper so the AST policy can remain stricter.

### 2. Pin the image

The job image includes only:

- Python 3.12 at a pinned base-image digest;
- `python-docx` and explicitly approved support libraries at exact hashes;
- fonts and locale required by the design contract;
- the read-only helper module;
- a non-root user and fixed working directory.

The service records the job image digest and package/font inventory in every response. The job image contains no API keys and no Docker client.

### 3. Run container structure checks

```powershell
docker build -f Dockerfile.docx-sandbox-job -t blueprint-docx-job:test .
docker image inspect blueprint-docx-job:test
pytest docx_sandbox/tests/test_runner.py -q
```

### 4. Commit checkpoint

```text
Build the immutable DOCX authoring job image

This adds the minimal non-root runtime used for generated document programs.
Pinned dependencies, fixed paths, bounded outputs, and a content-free execution
report make runs reproducible and keep application secrets out of the image.
```

## Task 4: Implement the container runner with hard limits

### 1. Write fake-engine unit tests

Model the engine behind a protocol so unit tests assert the exact launch configuration:

```python
class ContainerEngine(Protocol):
    def run_job(self, spec: JobSpec) -> JobResult: ...


expected = JobSpec(
    image_digest=settings.job_image_digest,
    network_mode="none",
    read_only_root=True,
    user="65532:65532",
    memory_bytes=512 * 1024 * 1024,
    nano_cpus=1_000_000_000,
    pids_limit=64,
    timeout_seconds=45,
    cap_drop=("ALL",),
    no_new_privileges=True,
)
```

Test cleanup on success, timeout, engine error, malformed output, and client cancellation. Test that labels contain only the opaque job ID and expiry—not prompts or content.

### 2. Implement a Docker-engine adapter

The sandbox service may access a dedicated engine on an isolated host. Do not mount a general production host Docker socket into an internet-facing application container. The service validates the configured immutable job-image digest at startup and refuses mutable tags.

Collect bounded stdout/stderr, exit code, wall time, peak memory when available, output names/sizes/hashes, and termination reason. Always stop and remove the disposable job container in a `finally` block.

### 3. Run the gated integration test

```powershell
$env:RUN_DOCX_SANDBOX_INTEGRATION='1'
pytest docx_sandbox/tests/integration/test_job_container.py -q
```

Integration cases include valid DOCX generation, attempted network access, timeout loop, memory exhaustion, fork attempt, root-filesystem write, and oversized output.

### 4. Commit checkpoint

```text
Execute generated DOCX code in disposable containers

This runner enforces no-network, non-root, read-only, capability, PID, CPU,
memory, time, and output limits for every job. Cleanup and evidence collection
are covered for both successful and terminated executions.
```

## Task 5: Expose an authenticated private API

### 1. Write failing API tests

Test:

- health/readiness exposes version and configured image digest only;
- missing or invalid service authentication is rejected;
- replayed job IDs return the same completed result or a conflict, never a second execution;
- request size and concurrency limits are enforced;
- policy rejection never invokes the engine;
- logs redact program, manifest, DOCX bytes, tokens, and secrets;
- success streams the artifact and structured evidence with verified hashes.

### 2. Implement the FastAPI boundary

```python
@router.post("/v1/jobs", response_model=ExecuteResponse)
def execute_docx_job(
    request: ExecuteRequest,
    _: None = Depends(require_service_auth),
    runner: SandboxRunner = Depends(get_runner),
):
    report = inspect_program(request.program)
    if not report.allowed:
        return ExecuteResponse.policy_rejected(report)
    return runner.execute(request)
```

Use constant-time secret comparison or workload identity. Bind the service only to the private deployment network. Add rate/concurrency limiting in the service, not solely at the reverse proxy.

Run:

```powershell
pytest docx_sandbox/tests/test_api.py docx_sandbox/tests/test_runner.py -q
```

### 3. Commit checkpoint

```text
Expose the private DOCX sandbox service

This adds authenticated, replay-safe job submission with request, concurrency,
and logging controls. The API returns only bounded artifacts and execution
evidence and is designed for private-network access from the worker.
```

## Plan 2 completion gate

```powershell
pytest docx_sandbox/tests -q -m "not integration"
$env:RUN_DOCX_SANDBOX_INTEGRATION='1'
pytest docx_sandbox/tests/integration -q
```

Before deployment, manually inspect the resulting container launch configuration, confirm the job cannot reach the network or application environment, and run the hostile corpus. Plan 2 is complete only when arbitrary LLM output cannot select its command, environment, mounts, image, or output paths and each run occurs in a fresh bounded job container.
