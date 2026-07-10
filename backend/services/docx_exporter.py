from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement


def _add_word_equation(paragraph, expression: str) -> None:
    math = OxmlElement("m:oMath")
    run = OxmlElement("m:r")
    text = OxmlElement("m:t")
    text.text = expression
    run.append(text)
    math.append(run)
    paragraph._p.append(math)


def build_assessment_docx(*, assessment_id: int, prompt_id: int,
                          condition_label: str, course: str, topic: str,
                          questions: list[dict]) -> bytes:
    document = Document()
    document.add_heading("Blueprint Lab Assessment", level=1)
    document.add_paragraph(f"Assessment ID: {assessment_id}")
    document.add_paragraph(f"Prompt ID: {prompt_id}")
    document.add_paragraph(f"Experiment Condition: {condition_label}")
    document.add_paragraph(f"Course: {course}")
    document.add_paragraph(f"Topic: {topic}")

    document.add_heading("Generated Questions", level=2)
    for index, question in enumerate(questions, start=1):
        metadata = question.get("metadata", {})
        if metadata.get("question_title"):
            document.add_heading(metadata["question_title"], level=3)
        if metadata.get("concept_map_bridge"):
            document.add_paragraph(f"Concept-Map Bridge: {metadata['concept_map_bridge']}")
        if metadata.get("materials_science_context"):
            document.add_paragraph(f"Materials Science Context: {metadata['materials_science_context']}")
        document.add_paragraph(f"Q{index}. {question['body']}")
        for option in question.get("options", []):
            suffix = " [correct]" if option.get("is_correct") else ""
            document.add_paragraph(f"- {option['body']}{suffix}")

    document.add_heading("Solutions", level=2)
    for index, question in enumerate(questions, start=1):
        answer = question.get("model_answer")
        if not answer:
            correct = [option["body"] for option in question.get("options", []) if option.get("is_correct")]
            answer = correct[0] if correct else "No solution provided."
        document.add_paragraph(f"Q{index}. {answer}")
        for equation in question.get("equations", []):
            paragraph = document.add_paragraph(f"{equation['label']}: ")
            _add_word_equation(paragraph, equation["expression"])

    document.add_heading("Assessment Quality Check", level=2)
    for index, question in enumerate(questions, start=1):
        for check in question.get("quality_check", []):
            document.add_paragraph(
                f"Q{index} - {check['criterion']}: {check['rating']}/5 - {check['comment']}"
            )

    document.add_heading("Suggested Revision Options", level=2)
    for index, question in enumerate(questions, start=1):
        for revision in question.get("revision_options", []):
            document.add_paragraph(f"Q{index}: {revision}")

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
