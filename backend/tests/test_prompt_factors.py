from backend.schemas.experiment_schema import PromptFactors
from backend.services.prompt_factors import build_condition_label, build_research_prompt


def test_condition_label_records_each_factor_state():
    label = build_condition_label(PromptFactors(concept_bridge=True, reference_content=True))
    assert label == "ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF"


def test_openai_prompt_uses_markdown_structure_and_enabled_factors():
    prompt = build_research_prompt(
        prompt_structure="openai", course="MSE302",
        topic="Gibbs free energy and phase equilibrium",
        learning_objectives="Connect chemical potential to phase stability.",
        assessment_type="mixed", difficulty="intermediate", number_of_questions=1,
        factors=PromptFactors(concept_bridge=True, reference_content=True, reasoning_guidance=True),
        factor_inputs={"concept_bridge": "Vectors", "reference_content": "Use SI", "reasoning_guidance": "Show key steps"},
    )
    assert "# Role" in prompt
    assert "# Goal" in prompt
    assert "## Concept Bridge" in prompt
    assert "## Few-shot Examples" not in prompt
    assert "## Reference Content" in prompt
    assert "## Reasoning Guidance" in prompt
    assert "Show key steps" in prompt
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
