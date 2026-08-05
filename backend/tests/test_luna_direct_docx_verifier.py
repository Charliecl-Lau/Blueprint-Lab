from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.oxml import OxmlElement

from backend.services.luna_direct_docx_verifier import LunaDirectDocxVerifier


ASSESSMENT = {
    "questions": [
        {
            "body": "Calculate the equilibrium force.",
            "model_answer": "The equilibrium force is ten newtons.",
            "equations": [
                {"label": "force", "expression": "F = 10 N", "location": "solution"}
            ],
        }
    ]
}


def fixture_docx(*, question=True, solution=True, equation=True, placeholder=False):
    document = Document()
    if question:
        document.add_paragraph(ASSESSMENT["questions"][0]["body"])
    if solution:
        document.add_paragraph(ASSESSMENT["questions"][0]["model_answer"])
    if placeholder:
        document.add_paragraph("[[EQ:force]]")
    if equation:
        paragraph = document.add_paragraph()
        math = OxmlElement("m:oMath")
        run = OxmlElement("m:r")
        text = OxmlElement("m:t")
        text.text = "F=10N"
        run.append(text)
        math.append(run)
        paragraph._p.append(math)
    target = BytesIO()
    document.save(target)
    return target.getvalue()


def without_main_document(content):
    source = ZipFile(BytesIO(content))
    target = BytesIO()
    with source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for item in source.infolist():
            if item.filename != "word/document.xml":
                output.writestr(item, source.read(item.filename))
    return target.getvalue()


def codes(report):
    return {issue.code for issue in report.issues}


def test_accepts_valid_structural_canonical_and_omml_docx():
    report = LunaDirectDocxVerifier().verify(fixture_docx(), ASSESSMENT)

    assert report.valid is True
    assert report.issues == ()


def test_rejects_corrupt_zip():
    report = LunaDirectDocxVerifier().verify(b"not-a-docx", ASSESSMENT)

    assert report.valid is False
    assert codes(report) == {"docx_package_invalid"}


def test_rejects_missing_main_document():
    report = LunaDirectDocxVerifier().verify(
        without_main_document(fixture_docx()), ASSESSMENT
    )

    assert "docx_package_invalid" in codes(report)


def test_rejects_missing_canonical_question_text():
    report = LunaDirectDocxVerifier().verify(fixture_docx(question=False), ASSESSMENT)

    assert "canonical_question_missing" in codes(report)


def test_rejects_missing_canonical_solution_text():
    report = LunaDirectDocxVerifier().verify(fixture_docx(solution=False), ASSESSMENT)

    assert "canonical_solution_missing" in codes(report)


def test_rejects_unresolved_equation_placeholder():
    report = LunaDirectDocxVerifier().verify(fixture_docx(placeholder=True), ASSESSMENT)

    assert "equation_placeholder_unresolved" in codes(report)


def test_rejects_assessment_equations_without_native_omml():
    report = LunaDirectDocxVerifier().verify(fixture_docx(equation=False), ASSESSMENT)

    assert "native_equation_missing" in codes(report)
