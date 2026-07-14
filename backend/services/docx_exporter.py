from io import BytesIO
from typing import Optional

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


def build_assessment_docx(*, run_id: int, prompt_id: int,
                          condition_code: str, run_number: int, course: str, topic: str,
                          questions: list[dict],
                          token_usage: Optional[dict] = None) -> bytes:
    document = Document()
    document.add_heading("Blueprint Lab Assessment", level=1)
    document.add_paragraph(f"Run ID: {run_id}")
    document.add_paragraph(f"Prompt ID: {prompt_id}")
    document.add_paragraph(f"Condition Code: {condition_code}")
    document.add_paragraph(f"Run Number: {run_number}")
    document.add_paragraph(f"Course: {course}")
    document.add_paragraph(f"Topic: {topic}")
    document.add_heading("End-to-end token usage", level=2)
    if token_usage is None or token_usage.get("recording_state") == "not_recorded":
        document.add_paragraph("Not recorded.")
    else:
        labels = (
            ("Input", "input_tokens"),
            ("Output", "output_tokens"),
            ("Total", "total_tokens"),
            ("Model calls", "model_calls"),
        )
        for label, key in labels:
            value = token_usage.get(key)
            document.add_paragraph(
                f"{label}: {value if value is not None else 'Not reported'}"
            )

    document.add_heading("Generated Questions", level=2)
    for index, question in enumerate(questions, start=1):
        metadata = question.get("metadata", {})
        if metadata.get("question_title"):
            document.add_heading(metadata["question_title"], level=3)
        if metadata.get("question_type"):
            document.add_paragraph(f"Question Type: {metadata['question_type']}")
        if metadata.get("difficulty_level"):
            document.add_paragraph(f"Difficulty Level: {metadata['difficulty_level']}")
        if metadata.get("intended_assessment_setting"):
            document.add_paragraph(f"Intended Assessment Setting: {metadata['intended_assessment_setting']}")
        if metadata.get("mse202_concepts"):
            document.add_paragraph(f"MSE202 Concept(s): {', '.join(metadata['mse202_concepts'])}")
        if metadata.get("mse302_concepts"):
            document.add_paragraph(f"MSE302 Concept(s): {', '.join(metadata['mse302_concepts'])}")
        if metadata.get("concept_map_bridge"):
            document.add_paragraph(f"Concept-Map Bridge: {metadata['concept_map_bridge']}")
        if metadata.get("materials_science_context"):
            document.add_paragraph(f"Materials Science Context: {metadata['materials_science_context']}")
        if metadata.get("estimated_time"):
            document.add_paragraph(f"Estimated Time: {metadata['estimated_time']}")
        if metadata.get("learning_objectives"):
            document.add_paragraph(f"Learning Objectives: {', '.join(metadata['learning_objectives'])}")
        if metadata.get("id_requirements"):
            document.add_paragraph(f"ID Requirements: {metadata['id_requirements']}")
        document.add_paragraph(
            f"Traceability IDs — Prompt Template: {metadata.get('prompt_template_id', 'Not Assigned')}, "
            f"Actual Prompt: {metadata.get('actual_prompt_id', 'Not Assigned')}, "
            f"Output: {metadata.get('output_id', 'Not Assigned')}, "
            f"Final Question: {metadata.get('final_question_id', 'Not Assigned')}"
        )
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
