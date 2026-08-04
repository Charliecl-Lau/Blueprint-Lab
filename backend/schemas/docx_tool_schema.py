"""Strict application-controlled protocol for the agentic DOCX backend."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ToolName = Literal[
    "create_document", "set_page_layout", "set_theme", "set_header_footer",
    "add_section", "add_heading", "add_content", "add_question", "add_equation",
    "add_solution", "add_answer_key", "add_quality_check", "add_callout",
    "add_table", "add_page_break", "move_block", "update_block_style",
    "remove_decorative_block", "finalize_document",
]
ThemeToken = Literal["academic_blue", "academic_gray", "accessible_high_contrast"]
StyleToken = Literal[
    "body", "compact", "display", "inline", "numbered_card",
    "plain_question", "solution_step", "answer_key", "quality_check",
    "info", "warning", "table_grid", "table_banded", "heading_1",
    "heading_2", "heading_3",
]
PageSizeToken = Literal["letter", "a4"]
OrientationToken = Literal["portrait", "landscape"]
AlignmentToken = Literal["left", "center", "right"]
SectionRole = Literal[
    "assessment_metadata", "questions", "solutions", "answer_key",
    "quality_check", "revision_options",
]

THEME_TOKENS = {"academic_blue", "academic_gray", "accessible_high_contrast"}
STYLE_TOKENS = {
    "body", "compact", "display", "inline", "numbered_card", "plain_question",
    "solution_step", "answer_key", "quality_check", "info", "warning",
    "table_grid", "table_banded", "heading_1", "heading_2", "heading_3",
}
PAGE_SIZE_TOKENS = {"letter", "a4"}
ORIENTATION_TOKENS = {"portrait", "landscape"}
ALIGNMENT_TOKENS = {"left", "center", "right"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FORBIDDEN_KEYS = {"path", "file_path", "xml", "raw_xml", "code", "python", "shell", "macro", "url", "font", "font_name", "color", "shading"}


class DocxToolCall(BaseModel):
    model_config = {"extra": "forbid"}

    operation_id: str = Field(min_length=1, max_length=128)
    tool: ToolName
    expected_workspace_revision: int = Field(ge=0)
    arguments: "DocxToolArguments"

    @model_validator(mode="after")
    def validate_capability_boundary(self):
        if not _SAFE_ID.fullmatch(self.operation_id):
            raise ValueError("invalid operation_id")
        block_tools = {
            "add_section", "add_heading", "add_content", "add_question",
            "add_equation", "add_solution", "add_answer_key",
            "add_quality_check", "add_callout", "add_table",
            "add_page_break",
        }
        if self.tool in block_tools and self.arguments.block_id is None:
            self.arguments.block_id = f"{self.operation_id}-block"[:128]
        arguments = self.arguments.model_dump(exclude_none=True)
        encoded = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 16_384:
            raise ValueError("tool arguments exceed byte limit")

        def visit(value, key=""):
            if key.lower() in _FORBIDDEN_KEYS:
                raise ValueError(f"forbidden tool argument: {key}")
            if isinstance(value, dict):
                for child_key, child in value.items():
                    visit(child, str(child_key))
            elif isinstance(value, list):
                if len(value) > 100:
                    raise ValueError("tool list exceeds item limit")
                for child in value:
                    visit(child, key)
            elif isinstance(value, str) and len(value) > 1000:
                raise ValueError("literal text exceeds limit")
        visit(arguments)

        required = {
            "add_equation": {"block_id", "question_id", "equation_id"},
            "add_content": {"block_id", "content_ref"},
            "add_question": {"block_id", "question_id"},
            "add_solution": {"block_id", "question_id"},
            "move_block": {"block_id", "parent_id"},
            "update_block_style": {"block_id", "style"},
            "remove_decorative_block": {"block_id"},
        }.get(self.tool, set())
        missing = required - arguments.keys()
        if missing:
            raise ValueError(f"missing arguments: {sorted(missing)}")
        if "theme" in arguments and arguments["theme"] not in THEME_TOKENS:
            raise ValueError("unknown theme token")
        if "style" in arguments and arguments["style"] not in STYLE_TOKENS:
            raise ValueError("unknown style token")
        if "page_size" in arguments and arguments["page_size"] not in PAGE_SIZE_TOKENS:
            raise ValueError("unknown page size token")
        if "orientation" in arguments and arguments["orientation"] not in ORIENTATION_TOKENS:
            raise ValueError("unknown orientation token")
        if "alignment" in arguments and arguments["alignment"] not in ALIGNMENT_TOKENS:
            raise ValueError("unknown alignment token")
        if "literal_text" in arguments:
            if self.tool not in {"add_heading", "add_callout"}:
                raise ValueError("literal text is restricted to decorative blocks")
            if len(arguments["literal_text"]) > 200:
                raise ValueError("decorative literal exceeds limit")
        ranges = {
            "margin_inches": (0.4, 2.0),
            "font_size_points": (8, 32),
            "spacing_points": (0, 72),
            "border_width_points": (0, 6),
            "columns": (1, 12),
            "level": (1, 3),
        }
        for key, (minimum, maximum) in ranges.items():
            if key in arguments:
                value = arguments[key]
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not minimum <= value <= maximum:
                    raise ValueError(f"{key} is outside the approved range")
        return self


class DocxToolArguments(BaseModel):
    """Closed union of the bounded arguments accepted by every tool."""

    model_config = {"extra": "forbid"}

    block_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    parent_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    question_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    equation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    content_ref: Optional[str] = Field(default=None, min_length=1, max_length=256)
    content_refs: Optional[list[str]] = Field(default=None, max_length=100)
    theme: Optional[ThemeToken] = None
    page_size: Optional[PageSizeToken] = None
    orientation: Optional[OrientationToken] = None
    alignment: Optional[AlignmentToken] = None
    style: Optional[StyleToken] = None
    role: Optional[SectionRole] = None
    literal_text: Optional[str] = Field(default=None, max_length=200)
    header_content_ref: Optional[str] = Field(default=None, max_length=256)
    footer_content_ref: Optional[str] = Field(default=None, max_length=256)
    alt_text: Optional[str] = Field(default=None, max_length=300)
    page_numbers: Optional[bool] = None
    keep_with_next: Optional[bool] = None
    level: Optional[int] = Field(default=None, ge=1, le=3)
    columns: Optional[int] = Field(default=None, ge=1, le=12)
    margin_inches: Optional[float] = Field(default=None, ge=0.4, le=2.0)
    font_size_points: Optional[float] = Field(default=None, ge=8, le=32)
    spacing_points: Optional[float] = Field(default=None, ge=0, le=72)
    border_width_points: Optional[float] = Field(default=None, ge=0, le=6)


DocxToolCall.model_rebuild()


class DocxDesignTurn(BaseModel):
    model_config = {"extra": "forbid"}
    rationale: str = Field(max_length=1000)
    operations: list[DocxToolCall] = Field(max_length=100)


class ReviewObservation(BaseModel):
    model_config = {"extra": "forbid"}
    page: Optional[int] = Field(default=None, ge=1)
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class DocxReviewTurn(BaseModel):
    model_config = {"extra": "forbid"}
    decision: Literal["approve", "revise", "reject"]
    observations: list[ReviewObservation] = Field(default_factory=list, max_length=100)
    operations: list[DocxToolCall] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def enforce_decision_contract(self):
        if self.decision == "approve" and self.operations:
            raise ValueError("approve cannot contain mutating operations")
        if self.decision == "revise" and not self.operations:
            raise ValueError("revise requires at least one operation")
        if self.decision == "reject" and self.operations:
            raise ValueError("reject cannot contain operations")
        return self
