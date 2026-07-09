from pydantic import BaseModel

class PromptGenerationResponse(BaseModel):
    generated_prompt: str
