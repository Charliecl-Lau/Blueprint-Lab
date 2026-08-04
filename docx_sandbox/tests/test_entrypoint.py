from docx_sandbox.job.entrypoint import program_line


def test_program_line_reports_only_generated_program_location():
    try:
        exec(compile("value = 1\nraise RuntimeError('secret')", "/job/program.py", "exec"))
    except RuntimeError as exc:
        assert program_line(exc) == 2


def test_program_line_ignores_non_program_frames():
    try:
        raise RuntimeError("secret")
    except RuntimeError as exc:
        assert program_line(exc) is None
