# Signed OMML Superscripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the complete signed value of an ungrouped Word-linear exponent inside its native OMML superscript.

**Architecture:** Extend the existing recursive-descent parser at the script-value boundary, where `^` and `_` consume their operands. A focused helper combines an optional ASCII `+`/`-` or Unicode minus sign with the following atom while leaving unsigned and grouped scripts unchanged.

**Tech Stack:** Python 3, python-docx OMML elements, lxml, pytest

## Global Constraints

- Preserve grouped scripts, unsigned scripts, and chained subscript/superscript behavior.
- Treat a sign without a following atom as malformed and retain the existing editable-text fallback.
- Do not modify prompt generation or preprocess equation strings with regex replacement.
- Do not include unrelated existing workspace changes in commits.
- Commit messages must contain a subject and explanatory paragraph body, with no attribution trailers.

---

### Task 1: Parse and serialize complete signed script values

**Files:**
- Modify: `backend/tests/test_omml.py`
- Modify: `backend/tests/test_docx_exporter.py`
- Modify: `backend/services/omml.py:119-138`

**Interfaces:**
- Consumes: `_LinearEquationParser._parse_atom() -> dict` and `parse_linear_expression(expression: str) -> dict`
- Produces: `_LinearEquationParser._parse_script_value() -> dict`, used only by `_parse_script()`

- [x] **Step 1: Add parser regression tests for signed exponent operands and malformed dangling signs**

```python
def test_linear_parser_falls_back_to_editable_text_for_malformed_input():
    assert parse_linear_expression("x_(") == {"type": "text", "text": "x_("}
    assert parse_linear_expression("K^-") == {"type": "text", "text": "K^-"}


def test_linear_parser_keeps_signed_values_inside_superscripts():
    for expression, sign, value in (
        ("K^-1", "-", {"type": "number", "value": "1"}),
        ("x^+n", "+", {"type": "symbol", "name": "n"}),
        ("10^−3", "−", {"type": "number", "value": "3"}),
    ):
        parsed = parse_linear_expression(expression)

        assert parsed["type"] == "superscript"
        assert parsed["superscript"] == {
            "type": "sequence",
            "items": [
                {"type": "operator", "value": sign},
                value,
            ],
        }
```

- [x] **Step 2: Run parser regressions and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_omml.py::test_linear_parser_keeps_signed_values_inside_superscripts -v
python -m pytest backend/tests/test_omml.py::test_linear_parser_falls_back_to_editable_text_for_malformed_input -v
```

Observed: both failed because the parser put the sign alone inside a superscript instead of combining it with the following atom or rejecting a dangling sign.

- [x] **Step 3: Add a DOCX-level OMML regression test**

```python
def test_docx_keeps_complete_signed_exponent_inside_omml_superscript():
    content = build_assessment_docx(
        run_id=30,
        prompt_id=31,
        condition_code="C001",
        run_number=1,
        course="MSE202",
        topic="Signed powers",
        questions=[{
            "metadata": {},
            "body": "Interpret the unit.",
            "options": [],
            "model_answer": "Use the unit shown.",
            "equations": [{
                "label": "InverseUnit",
                "expression": "K^-1",
                "location": "solution",
            }],
        }],
    )

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")

    root = etree.fromstring(document_xml)
    namespace = {
        "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    }
    superscripts = root.xpath("//m:sSup/m:sup", namespaces=namespace)

    assert len(superscripts) == 1
    assert "".join(superscripts[0].itertext()) == "-1"
```

- [x] **Step 4: Run the DOCX regression and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_docx_exporter.py::test_docx_keeps_complete_signed_exponent_inside_omml_superscript -v
```

Observed: FAIL because the `<m:sup>` element contained only `-`.

- [x] **Step 5: Implement signed script-value parsing**

```python
    def _parse_script(self) -> dict:
        node = self._parse_atom()
        while self._peek() in ("_", "^"):
            operator = self._take()
            script = self._parse_script_value()
            if operator == "_":
                node = {"type": "subscript", "base": node, "subscript": script}
            else:
                node = {"type": "superscript", "base": node, "superscript": script}
        return node

    def _parse_script_value(self) -> dict:
        sign = self._peek()
        if sign not in ("+", "-", "−"):
            return self._parse_atom()
        self._take()
        return _sequence([
            {"type": "operator", "value": sign},
            self._parse_atom(),
        ])
```

- [x] **Step 6: Run focused OMML tests and verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_omml.py backend/tests/test_docx_exporter.py -v
```

Observed: 10 tests passed.

- [x] **Step 7: Run the complete backend regression suite**

Run:

```powershell
python -m pytest backend/tests -v
```

Observed: 159 passed and 5 skipped. The only warning is the pre-existing pytest-asyncio default-loop-scope deprecation warning also present at baseline.

- [x] **Step 8: Inspect the scoped diff and commit once**

```powershell
git diff --check -- backend/services/omml.py backend/tests/test_omml.py backend/tests/test_docx_exporter.py docs/superpowers/plans/2026-07-16-signed-omml-superscripts.md
git diff -- backend/services/omml.py backend/tests/test_omml.py backend/tests/test_docx_exporter.py docs/superpowers/plans/2026-07-16-signed-omml-superscripts.md
git add backend/services/omml.py backend/tests/test_omml.py backend/tests/test_docx_exporter.py docs/superpowers/plans/2026-07-16-signed-omml-superscripts.md
git commit -m "Fix signed OMML superscripts" -m "This keeps ungrouped signed exponent values together when parsing Word-linear equations, preventing the magnitude from falling back to the baseline in generated DOCX files. Parser and document-level regressions cover ASCII and Unicode signs while preserving existing malformed-input fallback behavior."
```
