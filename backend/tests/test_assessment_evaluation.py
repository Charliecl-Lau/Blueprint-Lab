import json
from copy import deepcopy

import pytest

from backend.models import Assessment, Condition, Evaluation, Experiment, Prompt, Run
from backend.services.assessment_evaluation import (
    EVALUATION_PROGRESS_MESSAGES,
    EvaluationValidationError,
    build_evaluation_input,
    evaluate_question,
    persist_assessment_questions,
)
from backend.services.llm_client import LLMResult, TokenUsage, TruncatedResponseError
from backend.services.reproducibility import canonical_json, sha256_text


ORIGINAL_QUESTION = {
    "type": "long_answer",
    "metadata": {
        "question_title": "Chemical potential and phase stability",
        "question_type": "long_answer",
        "difficulty_level": "advanced",
        "intended_assessment_setting": "Homework",
        "mse202_concepts": ["Equilibrium"],
        "mse302_concepts": ["Chemical potential"],
        "concept_map_bridge": "Connects equilibrium to equal chemical potentials.",
        "materials_science_context": "Compares alpha and beta phases in an alloy.",
    },
    "body": "Explain which phase is stable at the stated temperature.",
    "options": [],
    "model_answer": "The phase with lower molar Gibbs free energy is stable.",
    "revision_options": ["Add numerical data.", "Ask for a phase diagram."],
}


VALID_EVALUATION = {
    "criteria": [
        {
            "criterion_key": "technical_correctness",
            "score": 2,
            "justification": "The temperature needed for a unique comparison is missing.",
            "strengths": ["Uses Gibbs free energy."],
            "weaknesses": ["Missing temperature."],
            "suggested_improvements": ["Supply a temperature."],
            "suggested_modifications": ["Add T = 800 K to the saved question in a new version."],
        },
        {
            "criterion_key": "course_alignment",
            "score": 5,
            "justification": "The concept bridge is central.",
            "strengths": ["Explicit bridge."],
            "weaknesses": [],
            "suggested_improvements": [],
            "suggested_modifications": [],
        },
        {
            "criterion_key": "blooms_alignment",
            "score": 5,
            "justification": "Students analyze stability.",
            "strengths": ["Observable analysis."],
            "weaknesses": [],
            "suggested_improvements": [],
            "suggested_modifications": [],
        },
        {
            "criterion_key": "clarity_solution",
            "score": 5,
            "justification": "The requested explanation is clear.",
            "strengths": ["Clear deliverable."],
            "weaknesses": [],
            "suggested_improvements": [],
            "suggested_modifications": [],
        },
        {
            "criterion_key": "materials_context",
            "score": 5,
            "justification": "The alloy phase context is authentic.",
            "strengths": ["Authentic alloy scenario."],
            "weaknesses": [],
            "suggested_improvements": [],
            "suggested_modifications": [],
        },
    ],
    "major_strengths": ["Strong concept bridge."],
    "major_weaknesses": ["Missing essential temperature."],
    "highest_priority_revision": "Supply the state temperature.",
    "recommended_instructor_action": "Major revision required",
}
VALID_EVALUATION_JSON = json.dumps(VALID_EVALUATION)


class FakeLLM:
    model = "gemini-evaluator"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.fixture
def generation_fixture(test_db):
    experiment = Experiment(
        name="MSE assessment quality",
        description="Evaluate generated assessments.",
        topic_area="Materials thermodynamics",
        research_question="Are generated questions instructor-ready?",
        status="active",
        course="MSE302",
        topic="Phase stability",
        learning_objectives="Analyze phase stability using chemical potential.",
        assessment_type="long_answer",
        difficulty="advanced",
        number_of_questions=1,
        cognitive_demand="evaluate_create",
        additional_instruction="Use an alloy context.",
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C101",
        prompt_structure="openai",
        concept_bridge_enabled=True,
        factor_configuration={"concept_bridge": True},
        factor_inputs={"concept_bridge": "MSE202 equilibrium to MSE302 chemical potential"},
        condition_label="Concept bridge enabled",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="evaluating_quality",
        provider="google",
        model="gemini-generation",
        version="generation-v1",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        model_call_count=1,
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="System",
        structure_input="Input",
        actual_prompt="Generate the assessment.",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="template-v1",
        actual_prompt_generator_version="generator-v1",
        generation_context="Course evidence",
        generation_envelope_hash="b" * 64,
    )
    parsed = {"questions": [deepcopy(ORIGINAL_QUESTION)]}
    run.assessment = Assessment(
        raw_response_text=canonical_json(parsed),
        parsed_json=parsed,
        output_hash="c" * 64,
        schema_version="1.0",
    )
    test_db.add(experiment)
    test_db.commit()
    return run


def successful_result(raw_text=VALID_EVALUATION_JSON):
    return LLMResult(
        raw_text=raw_text,
        provider_request_id="evaluation-response-1",
        model_name="gemini-evaluator",
        model_version="evaluation-v1",
        finish_reason="STOP",
        usage=TokenUsage(12, 8, 20, None, 2, {}),
    )


def test_persist_questions_uses_canonical_content_without_mutating_assessment(
    test_db, generation_fixture
):
    before = deepcopy(generation_fixture.assessment.parsed_json)

    questions = persist_assessment_questions(test_db, generation_fixture.assessment)
    repeated = persist_assessment_questions(test_db, generation_fixture.assessment)

    assert [item.ordinal for item in questions] == [0]
    assert questions[0].content_hash == sha256_text(canonical_json(ORIGINAL_QUESTION))
    assert repeated[0].id == questions[0].id
    assert generation_fixture.assessment.parsed_json == before


def test_evaluate_question_saves_finalized_llm_criteria_and_authoritative_total(
    test_db, generation_fixture
):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    llm = FakeLLM(successful_result())
    progress = []

    evaluation = evaluate_question(test_db, generation_fixture, question, llm, progress.append)

    assert evaluation.evaluation_type == "llm"
    assert evaluation.status == "finalized"
    assert evaluation.weighted_score == 82.0
    assert evaluation.critical_gate == "FAIL"
    assert evaluation.overall_decision == "Not ready – critical issue"
    assert evaluation.evaluation_model == "gemini-evaluator"
    assert evaluation.evaluation_model_version == "evaluation-v1"
    assert len(evaluation.criteria) == 5
    technical = next(
        item
        for item in evaluation.criteria
        if item.criterion_key == "technical_correctness"
    )
    assert technical.justification.startswith("The temperature")
    assert evaluation.highest_priority_revision == "Supply the state temperature."
    assert generation_fixture.assessment.parsed_json["questions"][0] == ORIGINAL_QUESTION
    assert progress == list(EVALUATION_PROGRESS_MESSAGES)
    assert generation_fixture.total_tokens == 35
    assert generation_fixture.model_call_usages[-1].stage == "evaluation"


def test_evaluator_receives_immutable_question_rubric_and_research_context(
    test_db, generation_fixture
):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    llm = FakeLLM(successful_result())

    evaluate_question(test_db, generation_fixture, question, llm, lambda message: None)

    call = llm.calls[0]
    payload = json.loads(call["user_message"])
    assert payload["saved_assessment"]["question"] == ORIGINAL_QUESTION
    assert payload["saved_assessment"]["model_answer"] == ORIGINAL_QUESTION["model_answer"]
    assert payload["saved_assessment"]["content_hash"] == question.content_hash
    assert payload["rubric"]["version"] == "2026-07-16"
    assert payload["experiment_requirements"]["course"] == "MSE302"
    assert payload["prompt_design_factors"]["configuration"] == {"concept_bridge": True}
    assert "must not modify" in payload["evaluation_instruction"].lower()
    assert call["model_settings"] == {"temperature": 0}


def test_build_evaluation_input_rejects_changed_assessment_content(test_db, generation_fixture):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    generation_fixture.assessment.parsed_json["questions"][0]["body"] = "Changed"

    with pytest.raises(EvaluationValidationError, match="content hash"):
        build_evaluation_input(generation_fixture, question)


def test_evaluate_question_marks_hash_mismatch_as_failed_before_provider_call(
    test_db, generation_fixture
):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    changed = deepcopy(generation_fixture.assessment.parsed_json)
    changed["questions"][0]["body"] = "Changed"
    generation_fixture.assessment.parsed_json = changed
    test_db.commit()
    llm = FakeLLM(successful_result())

    with pytest.raises(EvaluationValidationError, match="content hash"):
        evaluate_question(test_db, generation_fixture, question, llm, lambda message: None)

    failed = test_db.query(Evaluation).filter_by(question_id=question.id).one()
    assert failed.status == "failed"
    assert llm.calls == []


def test_invalid_evaluator_output_creates_failed_record_without_changing_question(
    test_db, generation_fixture
):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    before = deepcopy(generation_fixture.assessment.parsed_json)
    llm = FakeLLM(successful_result('{"criteria": []}'))

    with pytest.raises(EvaluationValidationError, match="invalid structured response"):
        evaluate_question(test_db, generation_fixture, question, llm, lambda message: None)

    failed = test_db.query(Evaluation).filter_by(
        question_id=question.id, evaluation_type="llm"
    ).one()
    assert failed.status == "failed"
    assert generation_fixture.assessment.parsed_json == before


def test_truncated_evaluator_response_retains_usage_and_failed_attempt(
    test_db, generation_fixture
):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    truncated = successful_result("truncated")
    llm = FakeLLM(TruncatedResponseError(truncated))

    with pytest.raises(EvaluationValidationError, match="provider response was incomplete"):
        evaluate_question(test_db, generation_fixture, question, llm, lambda message: None)

    failed = test_db.query(Evaluation).filter_by(question_id=question.id).one()
    assert failed.status == "failed"
    assert generation_fixture.total_tokens == 35
    assert generation_fixture.model_call_usages[-1].total_tokens == 20
