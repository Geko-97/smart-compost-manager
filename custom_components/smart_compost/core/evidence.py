"""Evidence shared by the assessment and health modules.

Kept in its own module so `assessment` and `health` can both use it without
importing each other (docs/24_CODING_RULES.md: small, acyclic core).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Evidence:
    """One piece of support for a conclusion, with its source and recency.

    `source` is a machine-readable origin ("user_history", "materials_kb",
    "user_observations", "sensor:<entity>"), never a user-facing sentence
    (docs/24: no hardcoded English in the engine).
    """

    source: str
    parameter: str
    value: str | float | int | None
    timestamp: datetime
    role: str
