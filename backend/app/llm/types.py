"""Shared types between gateway.py and semantic_cache.py — split out to avoid
a circular import between the two."""
from __future__ import annotations

import enum


class TaskComplexity(enum.Enum):
    SIMPLE = "simple"  # structured/classification-style work (planner, fact-checker)
    COMPLEX = "complex"  # open-ended writing where quality matters most (synthesizer)
