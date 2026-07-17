from io import BytesIO

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from backend.services.omml import append_content, append_linear_math, append_math


METADATA_FIELDS = (
    ("Question Title", "question_title"),
    ("Question Type", "question_type"),
    ("Difficulty Level", "difficulty_level"),
    ("Intended Assessment Setting", "intended_assessment_setting"),
    ("MSE202 Concept(s)", "mse202_concepts"),
    ("MSE302 Concept(s)", "mse302_concepts"),
    ("Concept-Map Bridge", "concept_map_bridge"),
    ("Materials Science Context", "materials_science_context"),
    ("Estimated Time", "estimated_time"),
    ("Learning Objectives", "learning_objectives"),
    ("ID Requirements", "id_requirements"),
)

TRACEABILITY_FIELDS = (
    ("Prompt Template ID", "prompt_template_id"),
    ("Actual Prompt ID", "actual_prompt_id"),
    ("Output ID", "output_id"),
    ("Final Question ID", "final_question_id"),
)


def _configure_styles(document):
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.08

    for name, size, before, after in (
        ("Heading 1", 18, 18, 8),
        ("Heading 2", 14, 16, 7),
        ("Heading 3", 12, 13, 5),
    ):
        style = styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(31, 78, 121)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    choices = styles["List Bullet"]
    choices.font.name = "Arial"
    choices.font.size = Pt(11)
    choices.paragraph_format.left_indent = Inches(0.3)
    choices.paragraph_format.first_line_indent = Inches(-0.18)
    choices.paragraph_format.space_after = Pt(5)


def _text_value(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value) if value not in (None, "") else ""


def _metadata_rows(*, run_id, prompt_id, condition_code, run_number,
                   course, topic, questions):
    rows = [
        ("Run ID", str(run_id)),
        ("Prompt ID", str(prompt_id)),
        ("Condition Code", str(condition_code)),
        ("Run Number", str(run_number)),
        ("Course", str(course)),
        ("Topic", str(topic)),
    ]
    if not questions:
        return rows

    metadata = questions[0].get("metadata", {})
    for label, key in METADATA_FIELDS:
        value = _text_value(metadata.get(key))
        if value:
            rows.append((label, value))
    for label, key in TRACEABILITY_FIELDS:
        rows.append((label, _text_value(metadata.get(key)) or "Not Assigned"))
    return rows


def _set_cell_margins(cell, *, top=100, start=120, bottom=100, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for edge, value in (("top", top), ("start", start),
                        ("bottom", bottom), ("end", end)):
        element = margins.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def _set_table_geometry(table, widths):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table_width = table._tbl.tblPr.first_child_found_in("w:tblW")
    table_width.set(qn("w:w"), str(sum(width.twips for width in widths)))
    table_width.set(qn("w:type"), "dxa")
    for grid_column, width in zip(table._tbl.tblGrid.gridCol_lst, widths):
        grid_column.set(qn("w:w"), str(width.twips))


def _format_metadata_cell(cell, *, width, is_label):
    cell.width = width
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell)
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.05
    if is_label:
        paragraph.runs[0].bold = True
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "D9EAF7")
        cell._tc.get_or_add_tcPr().append(shading)


def _add_metadata_table(document, **metadata_inputs):
    rows = _metadata_rows(**metadata_inputs)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    widths = (Inches(2.05), Inches(4.45))
    _set_table_geometry(table, widths)

    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        _format_metadata_cell(cells[0], width=widths[0], is_label=True)
        _format_metadata_cell(cells[1], width=widths[1], is_label=False)


def _add_item_heading(document, *, kind, index, question):
    title = question.get("metadata", {}).get("question_title")
    text = f"{kind} {index}"
    if title:
        text += f": {title}"
    document.add_heading(text, level=3)


def _add_standalone_equation(document, equation):
    paragraph = document.add_paragraph(f"{equation['label']}: ")
    paragraph.paragraph_format.space_after = Pt(7)
    if equation.get("math"):
        append_math(paragraph, equation["math"])
    else:
        append_linear_math(paragraph, equation["expression"])


def build_assessment_docx(*, run_id: int, prompt_id: int,
                          condition_code: str, run_number: int, course: str, topic: str,
                          questions: list[dict]) -> bytes:
    document = Document()
    _configure_styles(document)
    document.add_heading("Blueprint Lab Assessment", level=1)
    document.add_heading("Assessment Metadata", level=2)
    _add_metadata_table(
        document,
        run_id=run_id,
        prompt_id=prompt_id,
        condition_code=condition_code,
        run_number=run_number,
        course=course,
        topic=topic,
        questions=questions,
    )

    document.add_heading("Generated Questions", level=2)
    for index, question in enumerate(questions, start=1):
        _add_item_heading(document, kind="Question", index=index, question=question)
        paragraph = document.add_paragraph()
        rendered_labels = append_content(
            paragraph,
            question.get("body_segments"),
            question["body"],
            equations=question.get("equations", []),
            location="question",
        )
        for option in question.get("options", []):
            suffix = " [correct]" if option.get("is_correct") else ""
            paragraph = document.add_paragraph(style="List Bullet")
            rendered_labels.update(append_content(
                paragraph,
                option.get("segments"),
                option["body"],
                equations=question.get("equations", []),
                location="question",
            ))
            paragraph.add_run(suffix)
        for equation in question.get("equations", []):
            if equation.get("location") != "question":
                continue
            if equation.get("label") in rendered_labels:
                continue
            _add_standalone_equation(document, equation)

    document.add_heading("Solutions", level=2)
    for index, question in enumerate(questions, start=1):
        answer = question.get("model_answer")
        if not answer:
            correct = [option["body"] for option in question.get("options", []) if option.get("is_correct")]
            answer = correct[0] if correct else "No solution provided."
        _add_item_heading(document, kind="Solution", index=index, question=question)
        paragraph = document.add_paragraph()
        rendered_labels = append_content(
            paragraph,
            question.get("model_answer_segments") if question.get("model_answer") else None,
            answer,
            equations=question.get("equations", []),
            location="solution",
        )
        for equation in question.get("equations", []):
            if equation.get("location") != "solution":
                continue
            if equation.get("label") in rendered_labels:
                continue
            _add_standalone_equation(document, equation)

    document.add_heading("Suggested Revision Options", level=2)
    for index, question in enumerate(questions, start=1):
        for revision in question.get("revision_options", []):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.add_run(f"Q{index}: ").bold = True
            paragraph.add_run(revision)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
