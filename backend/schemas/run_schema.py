from typing import Literal, Optional

from pydantic import BaseModel, Field


SourceRole = Literal["course_syllabus", "bridge_map", "few_shot_example", "rubric", "reference_content", "instructor_example"]


class SourceBinding(BaseModel):
    source_document_id: int
    role: SourceRole
    ordinal: int = Field(ge=0)


class ModelSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    version: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    seed: Optional[int] = None
    max_tokens: Optional[int] = None


class RunCreate(BaseModel):
    source_bindings: list[SourceBinding] = Field(default_factory=list)
    model_settings: Optional[ModelSettings] = None
    model_config = {"protected_namespaces": ()}


class RunSummary(BaseModel):
    id: int
    condition_id: int
    run_number: int
    status: Literal["pending", "prompting", "generating", "documenting", "complete", "error"]
    model_settings: dict
    model_config = {"from_attributes": True, "protected_namespaces": ()}
