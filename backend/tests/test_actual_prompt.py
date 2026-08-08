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
    assert openai_version == anthropic_version == "15"


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


def test_generation_and_structure_prompts_require_segmented_word_equations():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    for required_text in (
        "native Microsoft Word OMML",
        "equations[]",
        "expression",
        "Microsoft Word linear equation syntax",
        "sqrt(...)",
        "text segment",
        "math segment",
    ):
        assert required_text in generation_prompt
    assert "numeric assignment" in generation_prompt
    assert "structured math AST" not in generation_prompt
    assert "Do not create equation labels" in generation_prompt

    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert "native Microsoft Word OMML" in system_prompt
        assert "equations[]" in system_prompt
        assert "Microsoft Word linear equation syntax" in system_prompt
        assert "text and math segments" in system_prompt
        assert "structured math AST" not in system_prompt
        lowered = system_prompt.lower()
        assert (
            "forbid the model from creating labels" in lowered
            or "do not create labels" in lowered
        )


def test_generation_and_repair_prompts_delegate_labels_to_backend():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    repair_prompt = build_assessment_repair_system_prompt(OPENAI_ACTUAL_PROMPT)

    for prompt in (generation_prompt, repair_prompt):
        assert "Do not create" in prompt or "Do not create labels" in prompt
        assert "equations[]" in prompt
    assert "Audit every text segment" in repair_prompt


def test_openai_template_and_versions_require_typed_segments():
    prompt = render_openai()

    assert "ordered arrays of typed segments" in prompt
    assert "Do not create labels" in prompt
    assert actual_prompt.ACTUAL_PROMPT_GENERATOR_VERSION == "18"
    assert actual_prompt.OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION == "11"


def test_multistage_long_answer_prompt_contains_subpart_decomposition_rule():
    prompt = render_openai(
        assessment_type="long_answer",
        learning_objectives=[
            "Derive a stability criterion, compute limiting compositions, and interpret the phase behavior."
        ],
    )

    assert "Subpart Decomposition Rule" in prompt
    assert "multiple distinct cognitive tasks or dependent stages" in prompt
    assert "concept or principle, derivation, numerical application" in prompt


def test_single_step_short_answer_prompt_forbids_artificial_decomposition():
    prompt = render_openai(
        assessment_type="short_answer",
        learning_objectives=["State the Gibbs phase rule."],
    )

    assert "For short-answer questions, use subparts only" in prompt
    assert "single short conceptual question" in prompt
    assert "simple one-step calculation" in prompt


def test_multiple_choice_prompt_keeps_individual_mcqs_single_part():
    prompt = render_openai(assessment_type="mcq")

    assert "do not turn individual questions into multipart questions" in prompt
    assert "unless multipart multiple-choice questions are explicitly requested" in prompt


def test_subpart_rule_preserves_method_disclosure_protection():
    prompt = render_openai(assessment_type="long_answer")

    protection = (
        "Do not provide governing thermodynamic identities, equilibrium criteria, "
        "or other knowledge that students are expected to recall unless explicitly requested."
    )
    assert protection in prompt
    assert "without exposing solution scaffolding" in prompt
    assert "Do not name a governing equation, criterion, or method" in prompt


def test_subpart_rule_requires_exact_solution_mirroring():
    prompt = render_openai(assessment_type="long_answer")

    assert "exactly the same labels, order, and task boundaries" in prompt
    assert "Solution (a), Solution (b), and Solution (c)" in prompt
    assert "do not combine multiple student subparts" in prompt
    assert "Each solution subpart must end with the result or conclusion" in prompt


def test_missing_subparts_are_not_a_post_generation_repair_condition():
    repair_prompt = build_assessment_repair_system_prompt(render_openai())

    assert "Never add, remove, relabel, or restructure question subparts" in repair_prompt
    assert "subpart use is an observed generation outcome, not a repair condition" in repair_prompt


def test_both_structure_compilers_require_question_type_aware_subparts():
    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert "Subpart Decomposition Requirement" in system_prompt
        assert "multiple distinct cognitive tasks or dependent stages" in system_prompt
        assert "individual multiple-choice questions" in system_prompt.casefold()
        assert "same labels, order, and task boundaries" in system_prompt
        assert "must not reveal a governing equation, criterion, or method" in system_prompt
        assert "repair of a completed question that lacks subparts" in system_prompt


def test_generation_and_actual_prompts_require_guided_solution_derivations():
    generation_prompt = build_generation_system_prompt(render_openai())
    actual = render_openai()
    for prompt in (generation_prompt, actual):
        assert "continuous guided mathematical derivation" in prompt
        assert "Do not use labels such as 'Step 1'" in prompt or "Do not use labels such as \"Step 1\"" in prompt
        assert "do not treat a stated answer choice as a solution" in prompt
        assert "Each paragraph must perform exactly one logical operation" in prompt
        assert "Using the quotient rule" in prompt
        assert "Why the other choices are incorrect" in prompt
        assert "one separate line for every distractor" in prompt
        assert "short expressions" in prompt
        assert "alternating text and math segments" in prompt
        assert "Never place a short symbol or variable definition alone" in prompt
        assert "Do not jump from a governing equation to the final answer" in prompt
        assert "numerical comparison or logical test" in prompt
        assert "Check signs, dimensions, units" in prompt
        assert "For stability or equilibrium problems" in prompt
        assert "solve the resulting inequality or constraint" in prompt


def test_structure_prompts_require_inline_math_and_complete_derivations():
    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert "short expressions, parameter definitions, constants" in system_prompt
        assert "display=false" in system_prompt
        assert "complete instructor-facing derivation" in system_prompt
        assert "jumping from the governing relation to the final answer" in system_prompt


def test_structure_input_contains_details_and_enabled_factor_values_only():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives=["Apply the phase rule."],
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
        learning_objectives=["Apply the phase rule."],
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
        learning_objectives=["Apply the phase rule."],
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
        "learning_objectives": ["Apply the phase rule to alloy systems."],
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


def test_openai_prompt_omits_all_concept_bridge_guidance_when_disabled():
    prompt = render_openai()

    assert "concept bridge" not in prompt.casefold()
    assert "concept_map_bridge" in prompt
    assert '"concept_map_bridge": null' in prompt


def test_openai_prompt_includes_only_supplied_concept_bridge_when_enabled():
    supplied = "Connect equilibrium to chemical potential."
    prompt = render_openai(
        factors=PromptFactors(concept_bridge=True),
        factor_inputs={"concept_bridge": supplied},
    )

    assert prompt.count(supplied) == 3
    assert '"concept_map_bridge": "Connect equilibrium to chemical potential."' in prompt


def test_openai_template_demonstrates_required_typed_segments():
    prompt = render_openai()

    assert (
        '"body_segments": ['
    ) in prompt
    assert '"model_answer_segments": [' in prompt
    assert '"type": "text"' in prompt
    assert '"type": "math"' in prompt
    assert '"expression": "R = 8.314 J/(mol K)"' in prompt
    assert '"display": false' in prompt
    assert '"display": true' in prompt
    assert "contains no placeholder text" not in prompt
    assert "Use one math segment for a complete equality or derivation chain" in prompt
    assert "Do not create labels" in prompt
    assert "explicit lowercase component subscripts: x_a and x_b, y_a and y_b" in prompt
    assert '"expression": "G_mix/(R T) = x_a ln(x_a) + x_b ln(x_b)"' in prompt
    assert "x_A ln(x_A)" not in prompt
    assert '"mse202_concepts": ["Gibbs Phase Rule"]' in prompt
    assert '"mse302_concepts": ["Not Provided"]' in prompt
    assert '"learning_objectives": ["Apply the phase rule to alloy systems."]' in prompt


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
    assert "Connect chemical potential to phase stability." in prompt


def test_openai_template_handles_disabled_factors_and_optional_instruction():
    prompt = render_openai(factor_inputs={"few_shot": "must not appear"})
    instructed = render_openai(
        additional_instruction="  Use one laboratory scenario.  "
    )
    assert "Selected Prompt Design Factors:\nNone Selected" in prompt
    assert "concept bridge" not in prompt.casefold()
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
    assert "Return only the replacement object" in system_prompt
    assert "Preserve semantic meaning, numerical values, wording, notation" in system_prompt
    assert "Text segments must contain prose only" in system_prompt
    assert "move mathematical content into a math segment" in system_prompt
    assert "one math segment for a complete equality" in system_prompt
    assert "Do not create labels" in system_prompt
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
Return a JSON object with a top-level "questions" array and "assessment_metadata" object
Stop Rules
Stop after output"""

ANTHROPIC_ACTUAL_PROMPT = """<context>Course context</context>
<task>Generate questions</task>
<constraints>Use supplied facts</constraints>
<verification>Check correctness</verification>
<output_format>Return a JSON object with a top-level "questions" array and "assessment_metadata" object</output_format>
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
                'Output Format\nReturn a JSON object with a top-level "questions" array and "assessment_metadata" object\n',
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
