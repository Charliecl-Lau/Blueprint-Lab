from backend.schemas.experiment_schema import PromptFactors
from backend.services.prompt_generator import generate_prompt


def test_generate_prompt_serializes_first_call_input():
    result = generate_prompt(
        course="MSE302", topic="Phase equilibrium",
        learning_objectives="Relate Gibbs energy to phase stability.",
        assessment_type="mcq", difficulty="intermediate", number_of_questions=2,
        prompt_structure="anthropic", factors=PromptFactors(concept_bridge=True), factor_inputs={"concept_bridge": "Vectors"},
    )
    assert result.startswith("# Assessment Details")
    assert "Number of Questions: 2" in result
    assert "ConceptBridge=ON; FewShot=OFF; ReferenceContent=OFF; ReasoningGuidance=OFF" in result
    assert "Vectors" in result
