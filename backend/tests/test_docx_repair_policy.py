from backend.services.docx_repair_policy import DocxRepairPolicy
from backend.services.docx_verification import VerificationIssue, VerificationReport


def test_repair_policy_is_bounded_to_known_authoring_failures():
    policy = DocxRepairPolicy()
    assert policy.may_repair(VerificationReport(False, (VerificationIssue("semantic_mismatch"),)))
    assert not policy.may_repair(VerificationReport(False, (VerificationIssue("archive_bomb", repairable=False),)))
