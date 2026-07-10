from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.framework_templates import build_framework_system_prompt
from backend.services.llm_client import LLMClient
from backend.services.prompt_factors import build_research_prompt


def generate_prompt(*, course: str = "", topic: str, learning_objectives: str = "",
                    assessment_type: str = "mixed", difficulty: str = "",
                    number_of_questions: int = 1, prompt_structure: PromptStructure = "openai",
                    factors: PromptFactors = None, llm: LLMClient = None,
                    expectations: str = "", framework: str = "", personality: str = "",
                    prompt_length: str = "", result_length: str = "",
                    action_word_count: int = 0, mcq_count: int = 0,
                    long_answer_count: int = 0) -> str:
    if llm is not None:
        system_prompt = build_framework_system_prompt(
            framework=framework, personality=personality, prompt_length=prompt_length,
            result_length=result_length, action_word_count=action_word_count,
        )
        result = llm.generate_json(
            system_prompt=system_prompt,
            user_message=(f"Topic: {topic}\nExpectations: {expectations}\n"
                          f"MCQ count: {mcq_count}\nLong answer count: {long_answer_count}"),
        )
        if "generated_prompt" not in result:
            raise ValueError("LLM response missing 'generated_prompt' key")
        return result["generated_prompt"]

    return build_research_prompt(
        prompt_structure=prompt_structure, course=course, topic=topic,
        learning_objectives=learning_objectives, assessment_type=assessment_type,
        difficulty=difficulty, number_of_questions=number_of_questions,
        factors=factors or PromptFactors(),
    )
