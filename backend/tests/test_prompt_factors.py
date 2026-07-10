from backend.schemas.experiment_schema import PromptFactors
from backend.services.prompt_factors import build_condition_label, build_research_prompt


def test_condition_label_records_each_factor_state():
    label = build_condition_label(PromptFactors(course_bridge=True, documents=True))
    assert label == "CourseBridge=ON; FewShot=OFF; Documents=ON"


def test_openai_prompt_uses_markdown_structure_and_enabled_factors():
    prompt = build_research_prompt(
        prompt_structure="openai", course="MSE302",
        topic="Gibbs free energy and phase equilibrium",
        learning_objectives="Connect chemical potential to phase stability.",
        assessment_type="mixed", difficulty="intermediate", number_of_questions=1,
        factors=PromptFactors(course_bridge=True, documents=True),
    )
    assert "# Role" in prompt
    assert "# Goal" in prompt
    assert "## Course Bridge" in prompt
    assert "## Few-shot Examples" not in prompt
    assert "## Instructor Examples / Attached Documents" in prompt
    assert "CourseBridge=ON; FewShot=OFF; Documents=ON" in prompt
    assert "Return only valid JSON" in prompt


def test_anthropic_prompt_uses_reference_xml_structure():
    prompt = build_research_prompt(
        prompt_structure="anthropic", course="MSE302",
        topic="Laplace transforms in heat-transfer modeling",
        learning_objectives="Apply mathematical tools to thermodynamics reasoning.",
        assessment_type="short_answer", difficulty="intermediate", number_of_questions=1,
        factors=PromptFactors(),
    )
    for tag in ("context", "task", "constraints", "verification", "output_format", "reasoning_guidance"):
        assert prompt.count(f"<{tag}>") == 1
        assert prompt.count(f"</{tag}>") == 1
    assert "<role>" not in prompt
    assert "<prompt_design_factors>" not in prompt
    assert "Prompt Structure: anthropic" in prompt
    assert "Return only valid JSON" in prompt
