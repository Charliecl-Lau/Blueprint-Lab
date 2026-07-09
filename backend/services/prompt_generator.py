from backend.services.llm_client import LLMClient
from backend.services.framework_templates import build_framework_system_prompt


def generate_prompt(
    llm: LLMClient,
    topic: str,
    expectations: str,
    framework: str,
    personality: str,
    prompt_length: str,
    result_length: str,
    action_word_count: int,
    mcq_count: int,
    long_answer_count: int,
) -> str:
    system_prompt = build_framework_system_prompt(
        framework=framework,
        personality=personality,
        prompt_length=prompt_length,
        result_length=result_length,
        action_word_count=action_word_count,
    )
    user_message = (
        f"Topic: {topic}\n"
        f"Expectations: {expectations}\n"
        f"MCQ count: {mcq_count}\n"
        f"Long answer count: {long_answer_count}"
    )
    result = llm.generate_json(system_prompt=system_prompt, user_message=user_message)
    if "generated_prompt" not in result:
        raise ValueError(f"LLM response missing 'generated_prompt' key. Got keys: {list(result)}")
    return result["generated_prompt"]
