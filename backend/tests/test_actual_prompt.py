from pathlib import Path

import pytest

import backend.services.actual_prompt as actual_prompt
from backend.schemas.experiment_schema import PromptFactors
from backend.services.actual_prompt import (
    ActualPromptValidationError,
    build_assessment_repair_system_prompt,
    build_generation_system_prompt,
    build_condition_label,
    build_structure_input,
    render_openai_actual_prompt,
    validate_actual_prompt,
)
from backend.services.structure_system_prompts import get_structure_system_prompt


def test_provider_structures_are_distinct_and_versioned():
    openai_prompt, openai_version = get_structure_system_prompt("openai")
    anthropic_prompt, anthropic_version = get_structure_system_prompt("anthropic")
    assert openai_prompt
    assert anthropic_prompt
    assert openai_prompt != anthropic_prompt
    assert openai_version == anthropic_version == "10"


def test_provider_structures_require_questions_array_contract():
    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert '"questions"' in system_prompt
        assert "type" in system_prompt
        assert "body" in system_prompt
        assert "Assessment Quality Requirements" not in system_prompt
        assert "quality_check" not in system_prompt


def test_reference_prompt_does_not_require_assessment_quality_check():
    reference_prompt = Path("prompt/chatgpt-system-prompt.md").read_text(encoding="utf-8")

    assert "Assessment Quality Check" not in reference_prompt


def test_generation_and_structure_prompts_require_flat_word_equation_entries():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    for required_text in (
        "native Microsoft Word OMML",
        "equations[]",
        "expression",
        "Microsoft Word linear equation syntax",
        "equations = []",
        "sqrt(...)",
        "[[EQ:label]]",
    ):
        assert required_text in generation_prompt
    assert "numeric assignments" in generation_prompt
    assert "structured math AST" not in generation_prompt
    assert "body_segments" not in generation_prompt

    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert "native Microsoft Word OMML" in system_prompt
        assert "equations[]" in system_prompt
        assert "Microsoft Word linear equation syntax" in system_prompt
        assert "[[EQ:label]]" in system_prompt
        assert "structured math AST" not in system_prompt
        assert "body_segments" not in system_prompt


def test_generation_and_repair_prompts_require_location_specific_labels():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    repair_prompt = build_assessment_repair_system_prompt(OPENAI_ACTUAL_PROMPT)

    for prompt in (generation_prompt, repair_prompt):
        assert (
            "A label is prohibited from appearing in both question and solution content"
            in prompt
        )
        assert "create two equation entries with distinct labels" in prompt
    assert "Audit every equation label in every question" in repair_prompt


def test_openai_template_and_versions_require_location_specific_labels():
    prompt = render_openai()

    assert (
        "A label is prohibited from appearing in both question and solution content"
        in prompt
    )
    assert "two equation entries with distinct labels" in prompt
    assert actual_prompt.ACTUAL_PROMPT_GENERATOR_VERSION == "10"
    assert actual_prompt.OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION == "3"


def test_structure_input_contains_details_and_enabled_factor_values_only():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
        estimated_time_minutes=45,
        cognitive_demand="evaluate_create",
        additional_instruction="Use one laboratory scenario.",
        factors=PromptFactors(concept_bridge=True),
        factor_inputs={
            "concept_bridge": "Criterion for equilibrium",
            "few_shot": "must not appear",
        },
    )
    assert "Assessment Details" in text
    assert "Prompt Design Factors" in text
    assert "ConceptBridge=ON" in text
    assert "FewShot=OFF" in text
    assert "Criterion for equilibrium" in text
    assert "Cognitive Demand: Evaluate/Create" in text
    assert "Estimated Time: 45 minutes" in text
    assert "Additional Instruction: Use one laboratory scenario." in text
    assert "must not appear" not in text


def test_structure_input_omits_blank_additional_instruction():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
        estimated_time_minutes=45,
        cognitive_demand="remember_understand",
        additional_instruction="   ",
        factors=PromptFactors(),
        factor_inputs={},
    )

    assert "Cognitive Demand: Remember/Understand" in text
    assert "Additional Instruction" not in text


def test_structure_input_describes_pdfs_without_embedding_content():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
        estimated_time_minutes=45,
        cognitive_demand="apply_analyze",
        additional_instruction=None,
        factors=PromptFactors(reference_content=True),
        factor_inputs={},
        reference_pdf_filenames=["one.pdf", "two.pdf"],
    )

    assert "one.pdf, two.pdf" in text
    assert "supplied during final assessment generation" in text
    assert "PDF text" not in text


def test_condition_label_records_all_factor_states():
    assert build_condition_label(PromptFactors(concept_bridge=True)) == (
        "ConceptBridge=ON; FewShot=OFF; ReferenceContent=OFF; "
        "ReasoningGuidance=OFF"
    )


def render_openai(**overrides):
    values = {
        "course": "MSE202",
        "topic": "Gibbs Phase Rule",
        "learning_objectives": "Apply the phase rule to alloy systems.",
        "assessment_type": "short_answer",
        "difficulty": "medium",
        "number_of_questions": 2,
        "estimated_time_minutes": 30,
        "cognitive_demand": "apply_analyze",
        "additional_instruction": None,
        "factors": PromptFactors(),
        "factor_inputs": {},
    }
    values.update(overrides)
    return render_openai_actual_prompt(**values)


def test_openai_template_rendering_is_stable_and_preserves_json():
    first = render_openai()
    second = render_openai()
    assert first == second
    assert first.startswith("Role\n")
    assert '"questions": [' in first
    assert "{learning_objective}" not in first
    assert "Course:\nMSE202" in first
    assert "Cognitive Demand:\nApply/Analyze" in first
    assert "Estimated Time:\n30 minutes" in first
    assert '"type": "short_answer"' in first


def test_openai_template_demonstrates_required_equation_references():
    prompt = render_openai()

    assert (
        '"body": "The gas constant is [[EQ:gas_constant]]. '
        'Use [[EQ:question_equation]]."'
    ) in prompt
    assert '"model_answer": "Apply [[EQ:solution_equation]]."' in prompt
    assert '"label": "gas_constant"' in prompt
    assert '"expression": "R = 8.314 J/(mol K)"' in prompt
    assert '"label": "question_equation"' in prompt
    assert '"location": "question"' in prompt
    assert '"label": "solution_equation"' in prompt
    assert '"location": "solution"' in prompt
    assert "contains no placeholder text" not in prompt
    assert "[[EQ:label]] references are required equation references" in prompt
    assert "one reference for the complete equality or derivation chain" in prompt
    assert "Never join multiple references with an operator" in prompt


def test_openai_template_changes_only_substituted_values():
    baseline = render_openai(topic="Gibbs Phase Rule")
    changed = render_openai(topic="Chemical Potential")
    assert baseline != changed
    assert baseline.replace("Gibbs Phase Rule", "Chemical Potential") == changed


@pytest.mark.parametrize(
    ("course", "mse202", "mse302"),
    [
        (" mse202 ", "Gibbs Phase Rule", "Not Provided"),
        ("MSE302", "Not Provided", "Gibbs Phase Rule"),
        ("ENGR 101", "Not Provided", "Not Provided"),
    ],
)
def test_openai_template_maps_topic_to_course_concept(course, mse202, mse302):
    prompt = render_openai(course=course)
    assert f"MSE202 Concept(s):\n{mse202}" in prompt
    assert f"MSE302 Concept(s):\n{mse302}" in prompt


def test_openai_template_formats_enabled_factors_in_stable_order():
    prompt = render_openai(
        factors=PromptFactors(
            concept_bridge=True,
            few_shot=True,
            reference_content=True,
            reasoning_guidance=True,
        ),
        factor_inputs={
            "concept_bridge": "Connect chemical potential to phase stability.",
            "few_shot": "Example question and answer.",
            "reasoning_guidance": "Check phase-count assumptions.",
        },
        reference_pdf_filenames=["one.pdf", "two.pdf"],
    )
    blocks = [
        "Concept Bridge:\nConnect chemical potential to phase stability.",
        "Few-shot Examples:\nExample question and answer.",
        (
            "Reference Content:\nUse the attached PDF files in order as "
            "reference content: one.pdf, two.pdf."
        ),
        "Reasoning Guidance:\nCheck phase-count assumptions.",
    ]
    positions = [prompt.index(block) for block in blocks]
    assert positions == sorted(positions)
    assert (
        "Concept Map Bridge:\nConnect chemical potential to phase stability."
        in prompt
    )


def test_openai_template_handles_disabled_factors_and_optional_instruction():
    prompt = render_openai(factor_inputs={"few_shot": "must not appear"})
    instructed = render_openai(
        additional_instruction="  Use one laboratory scenario.  "
    )
    assert "Selected Prompt Design Factors:\nNone Selected" in prompt
    assert "Concept Map Bridge:\nNot Provided" in prompt
    assert "must not appear" not in prompt
    assert "Additional Instruction:" not in prompt
    assert (
        "Additional Instruction:\nUse one laboratory scenario." in instructed
    )


def test_openai_template_delegates_materials_context_derivation():
    assert (
        "Materials Science Context:\n"
        "Derive from the supplied course, topic, and learning objective."
    ) in render_openai()


def test_assessment_repair_prompt_preserves_content_and_reports_validation_error():
    system_builder = getattr(
        actual_prompt,
        "build_assessment_repair_system_prompt",
        None,
    )
    message_builder = getattr(
        actual_prompt,
        "build_assessment_repair_user_message",
        None,
    )

    assert system_builder is not None
    assert message_builder is not None

    system_prompt = system_builder(OPENAI_ACTUAL_PROMPT)
    user_message = message_builder(
        '{"questions":[{"body":"R = 8.314 J/(mol K)"}]}',
        "body: mathematical expression must use an equation reference",
    )

    assert OPENAI_ACTUAL_PROMPT in system_prompt
    assert "Return the complete corrected JSON object" in system_prompt
    assert "Preserve the assessment content" in system_prompt
    assert "contain zero raw mathematical syntax" in system_prompt
    assert "equals signs (=), underscores (_), carets (^)" in system_prompt
    assert "Scan body, every option body, and model_answer" in system_prompt
    assert "Variable-definition prose is not exempt" in system_prompt
    assert '"[[EQ:cp_symbol]] is the isobaric heat capacity"' in system_prompt
    assert (
        "one reference for the complete equality or derivation chain"
        in system_prompt
    )
    assert "Never place an operator between equation references" in system_prompt
    assert '"[[EQ:left]] = [[EQ:right]]"' in system_prompt
    assert "body: mathematical expression must use an equation reference" in user_message
    assert '"body":"R = 8.314 J/(mol K)"' in user_message


def test_openai_template_load_failure_is_classified(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.services.actual_prompt._OPENAI_TEMPLATE_PATH",
        tmp_path / "missing-template.md",
    )
    with pytest.raises(ActualPromptValidationError, match="cannot be loaded"):
        render_openai()


OPENAI_ACTUAL_PROMPT = """Role
Assessment author
Personality
Precise
Goal (Dynamic)
Generate questions
Prompt Parameters (Dynamic)
Use supplied parameters
Concept Mapping
Use supplied concepts
Prompt Design Factors
Use supplied factors
Constraints
Use supplied facts
Output Format
Return a JSON object with a top-level "questions" array
Stop Rules
Stop after output"""

ANTHROPIC_ACTUAL_PROMPT = """<context>Course context</context>
<task>Generate questions</task>
<constraints>Use supplied facts</constraints>
<verification>Check correctness</verification>
<output_format>Return a JSON object with a top-level "questions" array</output_format>
<reasoning_guidance>Use concise rationale</reasoning_guidance>"""


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [
        ("openai", ""),
        ("openai", f"```markdown\n{OPENAI_ACTUAL_PROMPT}\n```"),
        ("openai", f"Here is the prompt:\n{OPENAI_ACTUAL_PROMPT}"),
        (
            "openai",
            OPENAI_ACTUAL_PROMPT.replace(
                'Output Format\nReturn a JSON object with a top-level "questions" array\n',
                "",
            ),
        ),
        (
            "openai",
            OPENAI_ACTUAL_PROMPT.replace(
                "Concept Mapping\n", "Concept Mapping\nConcept Mapping\n"
            ),
        ),
        ("openai", OPENAI_ACTUAL_PROMPT + "\n{topic}"),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace("<verification>", "<context>")),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT + "\n<context>duplicate</context>"),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace("</task>", "")),
    ],
)
def test_invalid_actual_prompts_are_rejected(structure, raw_text):
    with pytest.raises(ActualPromptValidationError):
        validate_actual_prompt(structure, raw_text)


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [
        ("openai", OPENAI_ACTUAL_PROMPT.replace('top-level "questions" array', "JSON object")),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace('top-level "questions" array', "JSON object")),
    ],
)
def test_actual_prompts_without_questions_array_contract_are_rejected(structure, raw_text):
    with pytest.raises(ActualPromptValidationError, match="questions"):
        validate_actual_prompt(structure, raw_text)


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [("openai", OPENAI_ACTUAL_PROMPT), ("anthropic", ANTHROPIC_ACTUAL_PROMPT)],
)
def test_valid_actual_prompts_are_accepted_without_rewriting(structure, raw_text):
    assert validate_actual_prompt(structure, raw_text) is None
