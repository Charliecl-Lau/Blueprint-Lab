from typing import Optional

from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.actual_prompt import build_structure_input


def generate_prompt(*, course: str = "", topic: str, learning_objectives: str = "",
                    assessment_type: str = "mixed", difficulty: str = "",
                    number_of_questions: int = 1, prompt_structure: PromptStructure = "openai",
                    estimated_time_minutes: int = 30,
                    cognitive_demand: str = "remember_understand",
                    additional_instruction: Optional[str] = None,
                    factors: PromptFactors = None,
                    factor_inputs: dict[str, str] = None,
                    ) -> str:
    return build_structure_input(
        course=course, topic=topic,
        learning_objectives=learning_objectives, assessment_type=assessment_type,
        difficulty=difficulty, number_of_questions=number_of_questions,
        estimated_time_minutes=estimated_time_minutes,
        cognitive_demand=cognitive_demand,
        additional_instruction=additional_instruction,
        factors=factors or PromptFactors(), factor_inputs=factor_inputs or {},
    )
