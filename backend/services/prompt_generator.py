from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.prompt_factors import build_research_prompt


def generate_prompt(*, course: str = "", topic: str, learning_objectives: str = "",
                    assessment_type: str = "mixed", difficulty: str = "",
                    number_of_questions: int = 1, prompt_structure: PromptStructure = "openai",
                    factors: PromptFactors = None,
                    factor_inputs: dict[str, str] = None,
                    ) -> str:
    return build_research_prompt(
        prompt_structure=prompt_structure, course=course, topic=topic,
        learning_objectives=learning_objectives, assessment_type=assessment_type,
        difficulty=difficulty, number_of_questions=number_of_questions,
        factors=factors or PromptFactors(), factor_inputs=factor_inputs or {},
    )
