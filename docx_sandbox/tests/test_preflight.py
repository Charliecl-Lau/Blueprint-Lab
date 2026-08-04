import pytest
from docx_sandbox.preflight import inspect_program

@pytest.mark.parametrize("source", ["import subprocess", "import socket", "import requests", "import ctypes", "eval('1')", "import os\nos.system('id')", "import pickle", "open('/etc/passwd')", "open(path)"])
def test_hostile_programs_are_rejected(source):
    assert not inspect_program(source).allowed

def test_valid_fixture_uses_pinned_allowlist_and_paths():
    report = inspect_program("from docx import Document\nimport json\nd=Document()\nd.save('/output/assessment.docx')\nopen('/output/assessment_manifest.json','w').write(json.dumps({}))")
    assert report.allowed

def test_policy_report_has_stable_locations():
    issue = inspect_program("import subprocess").issues[0]
    assert issue.code == "forbidden_import" and issue.line == 1
