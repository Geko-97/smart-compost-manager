"""Manifest sanity (full hassfest/HACS validation lands in milestone M10)."""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "smart_compost"
    / "manifest.json"
)

REQUIRED_KEYS = (
    "domain",
    "name",
    "codeowners",
    "config_flow",
    "documentation",
    "integration_type",
    "iot_class",
    "issue_tracker",
    "version",
)


def test_manifest_has_all_required_keys() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in REQUIRED_KEYS:
        assert key in manifest, f"missing manifest key: {key}"

    assert manifest["domain"] == "smart_compost"
    assert manifest["config_flow"] is True
    # Calculated: the integration derives state, it never polls hardware.
    assert manifest["iot_class"] == "calculated"
    assert manifest["integration_type"] == "device"
    assert manifest["version"]
