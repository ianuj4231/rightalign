"""Provider-neutral LLM integration."""

from app.llm.factory import create_llm

__all__ = ["create_llm"]
