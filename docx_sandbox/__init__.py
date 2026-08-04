"""Private, disposable execution service for LLM-authored DOCX programs."""

from .contracts import ExecuteRequest, ExecuteResponse

__all__ = ["ExecuteRequest", "ExecuteResponse"]
