from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DistractorAnalysis(StrictModel):
    option_id: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ComputationalSolution(StrictModel):
    kind: Literal["computational"]
    knowns_and_target: list[str] = Field(min_length=1)
    governing_equation: str = Field(min_length=1)
    substitution: str = Field(min_length=1)
    calculation_steps: list[str] = Field(min_length=1)
    final_answer: str = Field(min_length=1)
    units: str = Field(min_length=1)
    physical_meaning: str = Field(min_length=1)
    distractor_analysis: list[DistractorAnalysis] = Field(min_length=4)


class ConceptualSolution(StrictModel):
    kind: Literal["conceptual"]
    governing_concept: str = Field(min_length=1)
    application_steps: list[str] = Field(min_length=1)
    option_elimination: list[DistractorAnalysis] = Field(min_length=4)
    conclusion: str = Field(min_length=1)


Solution = Annotated[
    Union[ComputationalSolution, ConceptualSolution], Field(discriminator="kind")
]


class AssessmentMetadata(StrictModel):
    title: str = Field(min_length=1)
    course: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    estimated_time_minutes: int = Field(ge=1)
    learning_objectives: list[str] = Field(min_length=1)


class RewrittenOption(StrictModel):
    id: str = Field(pattern=r"^[A-E]$")
    body: str = Field(min_length=1)
    is_correct: bool


class RewrittenQuestion(StrictModel):
    id: str = Field(min_length=1)
    source_question_id: str = Field(min_length=1)
    source_ordinal: int = Field(ge=0)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    options: list[RewrittenOption] = Field(min_length=5, max_length=5)
    solution: Solution

    @model_validator(mode="after")
    def validate_options(self):
        ids = [item.id for item in self.options]
        if len(set(ids)) != 5 or set(ids) != set("ABCDE"):
            raise ValueError("question options must use unique IDs A through E")
        if sum(item.is_correct for item in self.options) != 1:
            raise ValueError("question must have exactly one correct option")
        analyses = (
            self.solution.distractor_analysis
            if self.solution.kind == "computational"
            else self.solution.option_elimination
        )
        incorrect = {item.id for item in self.options if not item.is_correct}
        if {item.option_id for item in analyses} != incorrect:
            raise ValueError("solution must analyze every incorrect option exactly once")
        return self


class AnswerKeyEntry(StrictModel):
    question_id: str = Field(min_length=1)
    correct_option_id: str = Field(pattern=r"^[A-E]$")
    answer: str = Field(min_length=1)


class QualityCheckRow(StrictModel):
    question_id: str = Field(min_length=1)
    alignment: str = Field(min_length=1)
    correctness: str = Field(min_length=1)
    clarity: str = Field(min_length=1)
    accessibility: str = Field(min_length=1)


class RewrittenAssessmentManifest(StrictModel):
    schema_version: Literal["rewritten-assessment/1"]
    metadata: AssessmentMetadata
    questions: list[RewrittenQuestion] = Field(min_length=1)
    answer_key: list[AnswerKeyEntry] = Field(min_length=1)
    overall_connection: str = Field(min_length=1)
    quality_check: list[QualityCheckRow] = Field(min_length=1)
    revision_options: list[str] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_cross_references(self):
        ids = [item.id for item in self.questions]
        sources = [item.source_question_id for item in self.questions]
        ordinals = [item.source_ordinal for item in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question IDs must be unique")
        if len(sources) != len(set(sources)):
            raise ValueError("source question mappings must be unique")
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("source ordinals must be unique")
        if set(ordinals) != set(range(len(self.questions))):
            raise ValueError("source ordinals must cover the original assessment")
        key = {item.question_id: item for item in self.answer_key}
        quality_ids = [item.question_id for item in self.quality_check]
        if set(key) != set(ids) or len(self.answer_key) != len(ids):
            raise ValueError("answer key must cover every question exactly once")
        if set(quality_ids) != set(ids) or len(quality_ids) != len(ids):
            raise ValueError("quality check must cover every question exactly once")
        for question in self.questions:
            correct = next(item for item in question.options if item.is_correct)
            entry = key[question.id]
            if entry.correct_option_id != correct.id or entry.answer != correct.body:
                raise ValueError("answer key must agree with visible correct options")
        return self


class DocxProgramEnvelope(StrictModel):
    schema_version: Literal["docx-program-envelope/1"]
    language: Literal["python"]
    entrypoint: Literal["program.py"]
    program: str = Field(min_length=1, max_length=750_000)
    expected_outputs: list[Literal["assessment.docx", "assessment_manifest.json"]]
    grounding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_notes: str = Field(max_length=2000)

    @model_validator(mode="after")
    def exact_outputs(self):
        if self.expected_outputs != ["assessment.docx", "assessment_manifest.json"]:
            raise ValueError("expected_outputs must contain the two required files in order")
        return self


DOCX_PROGRAM_PROVIDER_SCHEMA = DocxProgramEnvelope.model_json_schema()
