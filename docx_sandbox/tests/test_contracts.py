from uuid import uuid4
import pytest
from pydantic import ValidationError
from docx_sandbox.contracts import ExecuteRequest, sha256_program

def request(**changes):
    program = "from docx import Document\nDocument().save('/output/assessment.docx')"
    data = dict(job_id=uuid4(), cycle_number=1, attempt_number=1, envelope_version="docx-program-envelope/1", program=program, program_sha256=sha256_program(program), grounding_sha256="a"*64)
    data.update(changes); return data

def test_request_binds_program_to_normalized_hash():
    assert ExecuteRequest(**request()).program_sha256 == sha256_program(request()["program"])

def test_request_forbids_arbitrary_execution_controls():
    with pytest.raises(ValidationError): ExecuteRequest(**request(command="rm -rf /"))

def test_wrong_program_hash_is_rejected():
    with pytest.raises(ValidationError): ExecuteRequest(**request(program_sha256="b"*64))
