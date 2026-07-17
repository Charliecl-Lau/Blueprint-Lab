# DOCX Metadata Table and Assessment Spacing Design

## Goal

Improve the generated Word assessment so its metadata is presented once in a readable table and its questions and solutions have the same clear visual separation as the supplied `MSE202_Gibbs_Phase_Rule_Assessment.docx` reference.

## Scope

This change is limited to the DOCX exporter and its tests. It does not change the generated assessment JSON, database schema, worker inputs, frontend viewer, equation representation, or previously generated artifacts.

## Metadata Table

Each generated DOCX contains exactly one metadata section near the beginning of the document. The section uses a two-column key-value table modeled on the reference document: a compact label column and a wider value column.

The table includes these run-level fields once:

- Run ID
- Prompt ID
- Condition Code
- Run Number
- Course
- Topic

It then includes the available metadata fields from the first generated question:

- Question Title
- Question Type
- Difficulty Level
- Intended Assessment Setting
- MSE202 Concept(s)
- MSE302 Concept(s)
- Concept-Map Bridge
- Materials Science Context
- Estimated Time
- Learning Objectives
- ID Requirements
- Prompt Template ID
- Actual Prompt ID
- Output ID
- Final Question ID

All questions in one exported assessment share the same metadata and generation inputs. Therefore, when several questions are present, the first question is the sole source for question metadata in the table. The exporter does not repeat metadata before later questions. When the questions list is empty, the table still contains the six run-level fields and omits question-specific rows.

Optional question-metadata rows are omitted when their values are absent or empty. List values are joined into readable comma-separated text. Traceability identifiers use `Not Assigned` when absent, preserving the existing exporter behavior.

## Questions and Solutions Layout

The document retains the existing title and top-level sections for generated questions, solutions, and suggested revision options. Within the questions and solutions sections, each item receives a distinct heading so readers can scan and navigate a multi-question assessment.

Question headings use the question number and, when available, the question title. The question body appears in a separate paragraph below the heading. Answer choices appear as indented list items with deliberate spacing between choices. Equations continue to render as native Word OMML, both inline and as standalone equation paragraphs.

Each solution receives a matching numbered heading. The worked answer begins in a separate paragraph with comfortable spacing from the heading and from the following solution. Standalone solution equations remain associated with the correct solution.

Paragraph and heading styles define spacing explicitly rather than relying on Word defaults. The layout provides visible separation:

- before each new question or solution;
- between a heading and its body;
- between question text and answer choices;
- between answer choices;
- around standalone equations; and
- before the next major section.

The spacing should resemble the supplied reference without copying its subject-specific content or making the reference file a runtime dependency.

## Implementation Structure

The existing `build_assessment_docx` entry point remains unchanged. Focused private helpers will configure document styles, build the metadata table, format table cells, create numbered item headings, and apply paragraph spacing. This keeps metadata construction and layout rules separate from content and OMML rendering.

The exporter continues to use `python-docx` for document structure and the existing `backend.services.omml` functions for equations. The reference DOCX is a design reference only and is not opened or required during application execution.

## Error and Compatibility Behavior

The exporter remains tolerant of the partial metadata dictionaries used by existing tests and legacy stored assessments. Missing optional metadata does not prevent export. Required runtime arguments and question bodies retain their existing behavior.

The change does not alter the document download interface or worker call signature. Existing documents are not rewritten.

## Testing and Verification

Automated tests will verify that:

- a multi-question export contains exactly one metadata table;
- the table includes all run-level fields;
- question metadata comes from the first question only;
- later question metadata is not repeated elsewhere;
- empty-question exports still include run-level metadata;
- question and solution headings are created for every item;
- relevant styles have explicit before/after spacing;
- answer choices use real Word list formatting rather than text-prefixed hyphens; and
- existing native OMML equation behavior remains intact.

A representative multi-question DOCX will be generated after implementation, rendered to page images, and inspected page by page. Verification will check table width and wrapping, cell padding, heading hierarchy, question/solution separation, answer-choice indentation, equation placement, page breaks, clipping, and overlap.
