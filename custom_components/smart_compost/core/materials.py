"""Material knowledge base (docs/08_MATERIALS_AND_BALANCE.md).

Users log plain words like "coffee grounds" — never C/N ratios. Internally
each material maps to a category used by the balance domain.

The rule that matters: an unrecognised material is UNKNOWN. The knowledge
base never guesses a category it does not contain, because a wrong category
would silently poison the balance conclusion (docs/04).
"""

from __future__ import annotations

import re
from enum import StrEnum

_NORMALIZE_PATTERN = re.compile(r"[\-_]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class MaterialCategory(StrEnum):
    """Simplified material taxonomy (user-facing vocabulary, docs/08)."""

    GREEN = "green"
    BROWN = "brown"
    STRUCTURAL = "structural"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


# Nitrogen-rich, moist, fast-decomposing.
_GREEN_MATERIALS = frozenset(
    {
        "food scraps",
        "food waste",
        "kitchen scraps",
        "plate scraps",
        "leftovers",
        "fruit",
        "fruit scraps",
        "fruit peelings",
        "vegetables",
        "vegetable scraps",
        "vegetable peelings",
        "grass clippings",
        "fresh grass",
        "lawn clippings",
        "garden trimmings",
        "hedge trimmings",
        "fresh leaves",
        "green leaves",
        "fresh pruning",
        "green waste",
        "coffee grounds",
        "ground coffee",
        "tea leaves",
        "manure",
        "herbivore manure",
        "seaweed",
    }
)

# Carbon-rich, dry, slow-decomposing.
_BROWN_MATERIALS = frozenset(
    {
        "dry leaves",
        "leaves",
        "autumn leaves",
        "straw",
        "hay",
        "sawdust",
        "wood dust",
        "wood shavings",
        "twigs",
        "branches",
        "bark",
        "nut shells",
        "corn cobs",
        "corn stalks",
        "pine needles",
        "dry grass",
        "dry clippings",
        "paper",
        "shredded paper",
        "newspaper",
    }
)

# Carbon-rich and mostly about structure/airflow rather than nutrition.
_STRUCTURAL_MATERIALS = frozenset(
    {
        "cardboard",
        "egg carton",
        "toilet rolls",
        "paper towel rolls",
        "wood chips",
        "wood chunks",
    }
)

# Neither green nor brown in any meaningful ratio (still compostable).
_NEUTRAL_MATERIALS = frozenset(
    {
        "eggshells",
        "egg shells",
        "shells",
        "seashells",
        "ash",
        "wood ash",
    }
)


def _normalize(raw: str) -> str:
    lowered = _NORMALIZE_PATTERN.sub(" ", raw.lower())
    return _WHITESPACE_PATTERN.sub(" ", lowered).strip()


_MATERIAL_TABLE: dict[str, MaterialCategory] = {
    **{name: MaterialCategory.GREEN for name in _GREEN_MATERIALS},
    **{name: MaterialCategory.BROWN for name in _BROWN_MATERIALS},
    **{name: MaterialCategory.STRUCTURAL for name in _STRUCTURAL_MATERIALS},
    **{name: MaterialCategory.NEUTRAL for name in _NEUTRAL_MATERIALS},
}


def classify_material(raw: str) -> MaterialCategory:
    """Classify a user-provided material name; UNKNOWN when not recognised."""
    normalized = _normalize(raw)
    if not normalized:
        return MaterialCategory.UNKNOWN
    return _MATERIAL_TABLE.get(normalized, MaterialCategory.UNKNOWN)


def known_material_examples() -> tuple[str, ...]:
    """A few canonical names, useful for docs and service descriptions."""
    return ("food_scraps", "dry_leaves", "cardboard", "coffee_grounds")
