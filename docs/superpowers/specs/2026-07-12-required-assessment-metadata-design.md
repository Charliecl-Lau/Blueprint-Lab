# Required Assessment Metadata Design

## Goal

Ensure every generated assessment question contains the metadata and review content needed by the Word export. Incomplete model output must be rejected instead of being accepted with empty defaults.

## Contract

Every question must contain `metadata`, `quality_check`, and `revision_options`. Metadata must contain `question_title`, `question_type`, `difficulty_level`, `intended_assessment_setting`, `mse202_concepts`, `mse302_concepts`, `concept_map_bridge`, and `materials_science_context`.

The concept lists must contain at least one item. Quality checks must contain at least one item. Revision options must contain two or three instructor-facing suggestions.

## Enforcement

The Pydantic response models will remove defaults from required fields and apply minimum-length constraints. The provider JSON schema will expose and require the same fields so Gemini is constrained to generate the complete shape. The provider schema and application validation must remain aligned.

`question_type` will be retained in metadata even though the question also has a top-level `type`, because the requested Word metadata explicitly includes Question Type.

## Testing

Focused schema tests will verify that complete output validates, missing required metadata fails, empty concept lists fail, missing quality checks fail, and revision-option counts outside two to three fail. Provider-schema tests will verify all fields are declared and required.

## Scope

This change updates generation and validation only. Rendering all required metadata in the Word document is a related exporter change but is outside this specific schema request.
