"""Replaceable AI adapters, prompts and test providers."""

from app.infrastructure.ai.fake_provider import ScriptedAIProvider
from app.infrastructure.ai.openai_provider import OpenAIProvider

__all__ = ["OpenAIProvider", "ScriptedAIProvider"]
