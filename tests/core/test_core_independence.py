"""The core package must stay independent of Home Assistant (docs/24)."""

from __future__ import annotations

from pathlib import Path

CORE_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "smart_compost" / "core"
)


def test_core_never_imports_home_assistant() -> None:
    core_files = sorted(CORE_DIR.glob("*.py"))
    assert core_files, "core package not found"

    for path in core_files:
        source = path.read_text(encoding="utf-8")
        assert "homeassistant" not in source, (
            f"{path.name} must not depend on Home Assistant"
        )


def test_core_never_imports_the_ha_layer() -> None:
    for path in sorted(CORE_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "from custom_components" not in source, (
            f"{path.name} must not reach into the integration package"
        )
        assert "from .." not in source, (
            f"{path.name} must not import the parent (HA) package"
        )
