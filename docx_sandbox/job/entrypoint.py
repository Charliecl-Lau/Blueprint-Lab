"""Container entrypoint: execute /job/program.py and emit content-free evidence."""
import json, os, runpy, sys, time, traceback
from pathlib import Path


def program_line(exc: Exception):
    """Return only the failing generated-program line, never source or values."""
    frames = traceback.extract_tb(exc.__traceback__)
    lines = [frame.lineno for frame in frames if frame.filename == "/job/program.py"]
    return lines[-1] if lines else None

def main() -> int:
    started = time.monotonic(); output = Path("/output")
    before = {p.name for p in output.iterdir()} if output.exists() else set()
    try:
        runpy.run_path("/job/program.py", run_name="__main__")
        if not output.exists(): raise RuntimeError("missing output directory")
        files = list(output.iterdir())
        names = {p.name for p in files}
        if names != {"assessment.docx", "assessment_manifest.json"} or any(p.is_symlink() or not p.is_file() for p in files): raise RuntimeError("invalid output set")
        manifest = json.loads((output / "assessment_manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict): raise RuntimeError("manifest must be an object")
        report = {"status": "succeeded", "output_names": sorted(names), "output_sizes": {p.name: p.stat().st_size for p in files}, "wall_time_ms": int((time.monotonic()-started)*1000)}
        print(json.dumps(report, sort_keys=True)); return 0
    except Exception as exc:
        print(json.dumps({"status":"execution_failed", "error": type(exc).__name__, "program_line": program_line(exc), "wall_time_ms": int((time.monotonic()-started)*1000)}), file=sys.stderr); return 1

if __name__ == "__main__": sys.exit(main())
