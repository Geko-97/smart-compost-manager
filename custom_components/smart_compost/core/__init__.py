"""Pure compost domain core.

Modules in this package must never import Home Assistant: the HA layer
translates config entries and entity state into these types, never the other
way around (docs/24_CODING_RULES.md, "domain first"). This invariant is
enforced by tests/core/test_core_independence.py.
"""
