from unittest.mock import MagicMock
import pytest
from backend.services.prompt_generator import generate_prompt


@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = {"generated_prompt": "You are an assessment generator. Topic: TCP/IP..."}
    return client


def test_generate_prompt_returns_string(mock_llm):
    result = generate_prompt(
        llm=mock_llm,
        topic="TCP/IP Networking",
        expectations="Test understanding of the three-way handshake",
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
        mcq_count=10,
        long_answer_count=3,
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_prompt_calls_llm_with_framework_system_prompt(mock_llm):
    generate_prompt(
        llm=mock_llm,
        topic="TCP/IP Networking",
        expectations="Test handshake understanding",
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
        mcq_count=10,
        long_answer_count=3,
    )
    call_args = mock_llm.generate_json.call_args
    assert "<context>" in call_args.kwargs["system_prompt"]
    assert "TCP/IP Networking" in call_args.kwargs["user_message"]


def test_generate_prompt_raises_on_missing_key(mock_llm):
    mock_llm.generate_json.return_value = {"wrong_key": "value"}
    with pytest.raises(ValueError, match="generated_prompt"):
        generate_prompt(
            llm=mock_llm,
            topic="TCP/IP",
            expectations="test",
            framework="forge",
            personality="formal",
            prompt_length="medium",
            result_length="medium",
            action_word_count=3,
            mcq_count=10,
            long_answer_count=3,
        )
