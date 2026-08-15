"""Shared LLM client factory.

Uses Groq-hosted open-source models (e.g. Llama 3.3 70B) instead of a
closed-source API — swap `GROQ_MODEL` in .env for any other Groq-hosted
model that supports tool calling (needed for `with_structured_output`).
"""
from __future__ import annotations

from functools import lru_cache

from langchain_groq import ChatGroq

from app.config import settings


@lru_cache
def get_llm(temperature: float = 0.0) -> ChatGroq:
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and fill it in before running the agent graph."
        )
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_tokens=4096,
    )
