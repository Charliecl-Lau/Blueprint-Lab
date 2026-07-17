# DOCX Metadata Table and Assessment Spacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate Word assessments with one first-question metadata table and clearly separated questions, choices, solutions, equations, and revision options.

**Architecture:** Keep `build_assessment_docx` as the public entry point and add focused private helpers in the existing exporter for styles, metadata rows, table geometry, and item headings. Preserve the current OMML rendering path while replacing repeated metadata paragraphs and text-prefixed answer choices with structured Word elements.

**Tech Stack:** Python 3.9, `python-docx`, WordprocessingML through `python-docx` OOXML primitives, pytest, existing Blueprint Lab OMML helpers, LibreOffice/Poppler render verification.

## Global Constraints

- Each DOCX contains exactly one metadata table.
- Run ID, Prompt ID, Condition Code, Run Number, Course, and Topic always appear once in the table.
- Question-specific metadata comes only from the first question.
- Empty question metadata rows are omitted, except traceability IDs default to `Not Assigned` when a first question exists.
- The `build_assessment_docx` signature, worker integration, and OMML behavior remain compatible.
- The reference DOCX is not a runtime dependency.
- Existing unrelated working-tree changes must remain untouched.
- Every commit has a subject and explanatory paragraph body, with no attribution trailers.

---

### Task 1: Lock the metadata and spacing contract in tests

**Files:**
- Modify: `backend/tests/test_docx_exporter.py:31-280`

**Interfaces:**
- Consumes: `build_assessment_docx(*, run_id: int, prompt_id: int, condition_code: str, run_number: int, course: str, topic: str, questions: list[dict]) -> bytes`
- Produces: Regression tests for metadata-table contents, first-question selection, empty assessments, item headings, real list paragraphs, and explicit style spacing.

- [ ] **Step 1: Add a table-text helper and a two-question fixture test**

Add this helper below `thermodynamic_equation_ast`:

```python
def table_rows(document):
    return [
        tuple(cell.text for cell in row.cells)
        for table in document.tables
        for row in table.rows
    ]
```

Add a test that builds two questions with different metadata and asserts that only the first metadata appears:

```python
def test_docx_uses_one_metadata_table_sourced_from_first_question():
    content = build_assessment_docx(
        run_id=12,
        prompt_id=34,
        condition_code="C101",
        run_number=2,
        course="MSE302",
        topic="Phase equilibrium",
        questions=[
            {
                "metadata": {
                    "question_title": "Shared equilibrium assessment",
                    "question_type": "long_answer",
                    "difficulty_level": "Medium",
                    "mse202_concepts": ["Gibbs Phase Rule"],
                    "prompt_template_id": "template-1",
                },
                "body": "Explain the single-phase region.",
                "options": [],
                "model_answer": "It has two degrees of freedom.",
                "revision_options": [],
            },
            {
                "metadata": {
                    "question_title": "This title must not become metadata",
                    "difficulty_level": "Hard",
                },
                "body": "Explain the eutectic point.",
                "options": [],
                "model_answer": "It is invariant at fixed pressure.",
                "revision_options": [],
            },
        ],
    )

    document = Document(BytesIO(content))
    rows = table_rows(document)
    assert len(document.tables) == 1
    assert ("Run ID", "12") in rows
    assert ("Prompt ID", "34") in rows
    assert ("Condition Code", "C101") in rows
    assert ("Run Number", "2") in rows
    assert ("Course", "MSE302") in rows
    assert ("Topic", "Phase equilibrium") in rows
    assert ("Question Title", "Shared equilibrium assessment") in rows
    assert ("Difficulty Level", "Medium") in rows
    assert ("MSE202 Concept(s)", "Gibbs Phase Rule") in rows
    assert ("Prompt Template ID", "template-1") in rows
    assert all("This title must not become metadata" not in value for row in rows for value in row)
    assert all(value != "Hard" for row in rows for value in row)
```

- [ ] **Step 2: Add empty-assessment and layout tests**

Add tests that assert run metadata still renders with no questions and that the document uses item headings, real list styles, and explicit spacing:

```python
def test_docx_empty_assessment_keeps_run_metadata_table():
    content = build_assessment_docx(
        run_id=1,
        prompt_id=2,
        condition_code="C100",
        run_number=1,
        course="ENGR 101",
        topic="Statics",
        questions=[],
    )
    document = Document(BytesIO(content))
    assert len(document.tables) == 1
    assert table_rows(document) == [
        ("Run ID", "1"),
        ("Prompt ID", "2"),
        ("Condition Code", "C100"),
        ("Run Number", "1"),
        ("Course", "ENGR 101"),
        ("Topic", "Statics"),
    ]


def test_docx_applies_spaced_item_styles_and_real_answer_choice_lists():
    content = build_assessment_docx(
        run_id=3,
        prompt_id=4,
        condition_code="C001",
        run_number=1,
        course="MSE202",
        topic="Phase rule",
        questions=[{
            "metadata": {"question_title": "Phase count"},
            "body": "How many phases coexist?",
            "options": [
                {"body": "One", "is_correct": False},
                {"body": "Three", "is_correct": True},
            ],
            "model_answer": "Three phases coexist.",
            "revision_options": [],
        }],
    )
    document = Document(BytesIO(content))
    paragraphs = document.paragraphs
    assert any(p.text == "Question 1: Phase count" and p.style.name == "Heading 3" for p in paragraphs)
    assert any(p.text == "Solution 1: Phase count" and p.style.name == "Heading 3" for p in paragraphs)
    choices = [p for p in paragraphs if p.text in {"One", "Three [correct]"}]
    assert len(choices) == 2
    assert all(p.style.name == "List Bullet" for p in choices)
    assert all(not p.text.startswith("- ") for p in choices)
    assert document.styles["Heading 2"].paragraph_format.space_before.pt >= 14
    assert document.styles["Heading 3"].paragraph_format.space_before.pt >= 12
    assert document.styles["Normal"].paragraph_format.space_after.pt >= 6
    assert document.styles["List Bullet"].paragraph_format.space_after.pt >= 4
```

- [ ] **Step 3: Update the existing rich-content assertions for table-based metadata**

Replace the paragraph-text assertions for run and metadata values with table-row assertions:

```python
    rows = table_rows(document)
    assert ("Run ID", "12") in rows
    assert ("Prompt ID", "34") in rows
    assert ("Condition Code", "C101") in rows
    assert ("Run Number", "2") in rows
    assert ("Concept-Map Bridge", "Connects MSE202 free energy to MSE302 phase stability.") in rows
```

Keep the solution, excluded-section, and OMML assertions unchanged.

- [ ] **Step 4: Run the focused tests and confirm the new contract fails**

Run:

```powershell
python -m pytest backend/tests/test_docx_exporter.py -q
```

Expected: the new tests fail because the exporter has no table, repeats metadata, prefixes choices with hyphens, and lacks the new headings and explicit spacing.

- [ ] **Step 5: Commit the failing contract tests**

```powershell
git add backend/tests/test_docx_exporter.py
git commit -m "Test DOCX metadata and spacing contract" -m "Define the single first-question metadata table and the structured spacing expected for questions, choices, and solutions. These failing tests protect the approved multi-question export behavior before the exporter implementation changes."
```

### Task 2: Implement the metadata table and readable assessment rhythm

**Files:**
- Modify: `backend/services/docx_exporter.py:1-114`
- Test: `backend/tests/test_docx_exporter.py`

**Interfaces:**
- Consumes: the unchanged `build_assessment_docx` arguments and existing `append_content`, `append_math`, and `append_linear_math` functions.
- Produces: `_configure_styles(document) -> None`, `_add_metadata_table(document, *, run_id, prompt_id, condition_code, run_number, course, topic, questions) -> None`, `_add_item_heading(document, *, kind, index, question) -> None`, and formatted DOCX bytes.

- [ ] **Step 1: Add style and metadata helper imports**

Extend the imports with:

```python
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
```

- [ ] **Step 2: Add explicit style configuration**

Add `_configure_styles(document)` before `build_assessment_docx`. Configure Arial typography, restrained blue headings, and explicit paragraph spacing:

```python
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
```

- [ ] **Step 3: Add metadata row normalization and table formatting**

Add helpers that create the six required run rows, append nonempty first-question metadata rows, and format the table:

```python
def _text_value(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value) if value not in (None, "") else ""


def _set_cell_margins(cell, *, top=100, start=120, bottom=100, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        element = margins.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def _metadata_rows(*, run_id, prompt_id, condition_code, run_number, course, topic, questions):
    rows = [
        ("Run ID", run_id),
        ("Prompt ID", prompt_id),
        ("Condition Code", condition_code),
        ("Run Number", run_number),
        ("Course", course),
        ("Topic", topic),
    ]
    if not questions:
        return [(label, str(value)) for label, value in rows]
    metadata = questions[0].get("metadata", {})
    fields = (
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
    for label, key in fields:
        value = _text_value(metadata.get(key))
        if value:
            rows.append((label, value))
    for label, key in (
        ("Prompt Template ID", "prompt_template_id"),
        ("Actual Prompt ID", "actual_prompt_id"),
        ("Output ID", "output_id"),
        ("Final Question ID", "final_question_id"),
    ):
        rows.append((label, _text_value(metadata.get(key)) or "Not Assigned"))
    return [(label, str(value)) for label, value in rows]
```

Add this table builder, which fixes the overall and per-column widths in DXA and applies readable cell padding:

```python
def _add_metadata_table(document, **metadata_inputs):
    rows = _metadata_rows(**metadata_inputs)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.autofit = False
    widths = (Inches(2.05), Inches(4.45))

    table_width = table._tbl.tblPr.tblW
    table_width.set(qn("w:w"), "9360")
    table_width.set(qn("w:type"), "dxa")
    for grid_column, width in zip(table._tbl.tblGrid.gridCol_lst, widths):
        grid_column.set(qn("w:w"), str(width.twips))

    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for cell, width in zip(cells, widths):
            cell.width = width
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_margins(cell)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.05
        cells[0].paragraphs[0].runs[0].bold = True
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "D9EAF7")
        cells[0]._tc.get_or_add_tcPr().append(shading)

    document.add_paragraph().paragraph_format.space_after = Pt(2)
```

- [ ] **Step 4: Restructure questions, choices, and solutions**

At the start of `build_assessment_docx`, call `_configure_styles(document)`, add the title, add a level-2 `Assessment Metadata` heading, and call `_add_metadata_table(...)`.

Remove all metadata paragraphs from the question loop. Add headings with:

```python
def _add_item_heading(document, *, kind, index, question):
    title = question.get("metadata", {}).get("question_title")
    text = f"{kind} {index}"
    if title:
        text += f": {title}"
    document.add_heading(text, level=3)
```

Write the question body to its own Normal paragraph. Write each option with `document.add_paragraph(style="List Bullet")`; do not add a textual hyphen. Keep `[correct]` as the existing suffix. Apply 5 points after standalone equation paragraphs.

Write each solution under its own `Solution N[: title]` heading and keep the answer in a separate Normal paragraph. Preserve all existing equation filtering and OMML calls.

Write revision options as real `List Bullet` paragraphs with a bold `Q{index}: ` prefix run followed by the revision text.

- [ ] **Step 5: Run the focused exporter tests**

Run:

```powershell
python -m pytest backend/tests/test_docx_exporter.py -q
```

Expected: all exporter tests pass, including the unchanged OMML regression tests.

- [ ] **Step 6: Run worker and full backend regression tests**

Run:

```powershell
python -m pytest backend/tests/test_worker.py backend/tests/test_end_to_end_run_lifecycle.py -q
python -m pytest backend/tests -q
```

Expected: both commands pass without changing the exporter call signature.

- [ ] **Step 7: Commit the exporter implementation**

```powershell
git add backend/services/docx_exporter.py
git commit -m "Format DOCX metadata and assessment sections" -m "Render run provenance and shared first-question metadata in one structured table, then apply explicit heading, paragraph, list, and equation spacing throughout questions and solutions. The exporter remains compatible with existing worker calls and native Word equation generation."
```

### Task 3: Render and inspect a representative multi-question document

**Files:**
- Create temporarily: `.runtime/docx-qa/multi-question-assessment.docx`
- Create temporarily: `.runtime/docx-qa/rendered/page-*.png`
- No committed source changes expected.

**Interfaces:**
- Consumes: final `build_assessment_docx` behavior from Task 2 and the document skill's `render_docx.py`.
- Produces: visual evidence that every page is readable and free of clipping, overlap, broken tables, and cramped sections.

- [ ] **Step 1: Generate a representative two-question DOCX**

Create `.runtime/docx-qa/generate_qa_doc.py` with this code and run it from the repository root:

```python
from pathlib import Path

from backend.services.docx_exporter import build_assessment_docx


output = Path(".runtime/docx-qa/multi-question-assessment.docx")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(build_assessment_docx(
    run_id=12,
    prompt_id=34,
    condition_code="C101",
    run_number=2,
    course="MSE202",
    topic="Gibbs Phase Rule",
    questions=[
        {
            "metadata": {
                "question_title": "Degrees of Freedom in a Binary Alloy",
                "question_type": "long_answer",
                "difficulty_level": "Medium",
                "intended_assessment_setting": "Midterm examination",
                "mse202_concepts": ["Gibbs Phase Rule", "binary phase diagrams"],
                "mse302_concepts": ["multiphase equilibrium"],
                "concept_map_bridge": "Connects phase counting to equilibrium phase-diagram constraints.",
                "materials_science_context": "Solidification of a binary solder alloy.",
                "estimated_time": "20 minutes",
                "learning_objectives": ["Identify components and phases", "Calculate degrees of freedom"],
                "id_requirements": "Show all substitutions and define each symbol.",
                "prompt_template_id": "template-1",
                "actual_prompt_id": "prompt-34",
                "output_id": "output-12",
                "final_question_id": "question-set-12",
            },
            "body": "Calculate the degrees of freedom in the homogeneous liquid region and explain the physical meaning.",
            "options": [],
            "model_answer": "For two components and one phase at fixed pressure, F = C - P + 1 = 2.",
            "equations": [{"label": "Phase rule", "expression": "F=C-P+1", "location": "solution"}],
            "revision_options": ["Reduce the task to identifying C and P.", "Add a phase-diagram interpretation."],
        },
        {
            "metadata": {"question_title": "Metadata that must not repeat", "difficulty_level": "Hard"},
            "body": "Which statement correctly describes a three-phase eutectic point at fixed pressure?",
            "options": [
                {"body": "It has two degrees of freedom.", "is_correct": False},
                {"body": "It is invariant.", "is_correct": True},
                {"body": "The phase compositions vary independently.", "is_correct": False},
            ],
            "model_answer": "With two components and three phases, F = 0, so the equilibrium is invariant.",
            "revision_options": ["Ask students to calculate F before selecting an answer.", "Remove one distractor."],
        },
    ],
))
```

Run:

```powershell
python .runtime\docx-qa\generate_qa_doc.py
```

Expected: `.runtime/docx-qa/multi-question-assessment.docx` exists and is nonempty.

- [ ] **Step 2: Render the document to PNG pages**

Run:

```powershell
python "C:\Users\yeekw\.codex\plugins\cache\openai-primary-runtime\documents\26.630.12135\skills\documents\render_docx.py" ".runtime\docx-qa\multi-question-assessment.docx" --output_dir ".runtime\docx-qa\rendered" --emit_pdf
```

Expected: `page-1.png` through the final page and a nonempty PDF are created.

- [ ] **Step 3: Inspect every rendered page at full resolution**

Open each `page-*.png` and verify:

- only one metadata table appears;
- the table fits within the margins and long values wrap cleanly;
- labels and values have sufficient cell padding;
- question and solution headings are visually distinct;
- body text, choices, and equations have visible breathing room;
- choices are indented and aligned under real bullet markers;
- page breaks do not strand headings or create large avoidable gaps; and
- no text, borders, equations, headers, or footers clip or overlap.

If any check fails, adjust `backend/services/docx_exporter.py`, rerun the focused and full backend tests, rerender, and inspect every page again.

- [ ] **Step 4: Confirm the working tree contains only intended source changes**

Run:

```powershell
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint-Lab status --short
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint-Lab diff --check
```

Expected: the user’s pre-existing changes remain present, no QA render is staged, and no whitespace errors exist in the files changed by this work.
