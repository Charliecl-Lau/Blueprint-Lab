from backend.services.research_system_prompt import BLUEPRINT_LAB_SYSTEM_PROMPT


def test_converted_system_prompt_preserves_research_requirements():
    assert "undergraduate MSE thermodynamics assessment" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "MSE202" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "MSE302" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Concept-Map Bridge" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Assessment Quality Check" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Suggested Revision Options" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "native Word equation" in BLUEPRINT_LAB_SYSTEM_PROMPT


def test_converted_system_prompt_removes_chat_only_behavior():
    assert "download link" not in BLUEPRINT_LAB_SYSTEM_PROMPT.lower()
    assert "Blueprint Check" not in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Do not provide only plain text in the chat" not in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Return only valid JSON" in BLUEPRINT_LAB_SYSTEM_PROMPT
