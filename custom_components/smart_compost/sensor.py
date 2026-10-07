"""Derived result entities for one compost bin.

Only derived entities are created (docs/13): physical measurements are
already entities in Home Assistant and are never duplicated here. Entities
subscribe to the per-bin coordinator, so a log service call updates them
immediately without polling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    BinRuntime,
    SmartCompostConfigEntry,
    SmartCompostCoordinator,
)
from .core.assessment import Assessment
from .core.model import ActionCode, CycleStage, MaturityState, Phase


def _hours(delta: timedelta) -> float:
    """Hours with at most two decimals — no false precision (docs/06 §11)."""
    return round(delta.total_seconds() / 3600.0, 2)


def _cycle_report_attributes(assessment: Assessment) -> dict[str, Any]:
    """Facts, comparison deltas and baseline of the reported cycle (M7).

    Missing sides stay out of the payload as None/absent — an unknown
    minus a number is still unknown, never a fabricated delta (docs/18).
    """
    report = assessment.cycle_report
    if report is None:
        return {}
    attributes: dict[str, Any] = {
        "cycle_id": report.cycle_id,
        "status": report.status.value,
        "started_at": report.started_at.isoformat(),
        "completed_at": (
            report.completed_at.isoformat()
            if report.completed_at is not None
            else None
        ),
        "duration_days": report.duration_days,
        "material_count": report.material_count,
        "observation_count": report.observation_count,
        "intervention_count": report.intervention_count,
        "temperature_samples": report.temperature_samples,
        "peak_temperature": report.peak_temperature,
        "thermophilic_hours": report.thermophilic_hours,
        "material_quantity": dict(report.material_quantity),
        "limitations": list(report.limitations),
        "output": (
            {
                "quantity_value": report.output.quantity_value,
                "quantity_unit": report.output.quantity_unit,
                "destination": report.output.destination,
                "notes": report.output.notes,
            }
            if report.output is not None
            else None
        ),
        "comparison": None,
        "baseline": None,
    }
    comparison = assessment.cycle_comparison
    if comparison is not None:
        attributes["comparison"] = {
            "previous_cycle_id": comparison.previous_cycle_id,
            "duration_days_delta": comparison.duration_days_delta,
            "material_count_delta": comparison.material_count_delta,
            "intervention_count_delta": comparison.intervention_count_delta,
            "peak_delta": comparison.peak_delta,
            "thermophilic_hours_delta": comparison.thermophilic_hours_delta,
            "material_quantity_delta": comparison.material_quantity_delta,
        }
    baseline = assessment.baseline
    if baseline is not None:
        attributes["baseline"] = {
            "completed_cycles": baseline.completed_cycles,
            "confidence": baseline.confidence,
            "median_duration_days": baseline.median_duration_days,
            "median_peak": baseline.median_peak,
            "limitations": list(baseline.limitations),
        }
    return attributes


def _maturity_attributes(assessment: Assessment) -> dict[str, Any]:
    """Readiness support, forecast window and caveats (M8, docs/07).

    The forecast is a window with its own confidence — never a date — and
    it is absent (None) rather than guessed when there is nothing honest
    to estimate (docs/07 §12).
    """
    maturity = assessment.maturity
    forecast = maturity.forecast
    return {
        "provenance": maturity.provenance.value,
        "confidence": maturity.confidence,
        "method": maturity.method.value if maturity.method is not None else None,
        "limitations": list(maturity.limitations),
        "why": [
            {
                "source": item.source,
                "parameter": item.parameter,
                "value": item.value,
            }
            for item in maturity.evidence
        ],
        "forecast": (
            {
                "min_days": forecast.min_days,
                "max_days": forecast.max_days,
                "confidence": forecast.confidence,
                "limitations": list(forecast.limitations),
            }
            if forecast is not None
            else None
        ),
    }


@dataclass(frozen=True, kw_only=True)
class SmartCompostSensorDescription(SensorEntityDescription):
    """Describes a derived Smart Compost sensor.

    `enum_type` drives the ENUM options list so state translations and the
    allowed values can never drift apart.
    """

    value_fn: Callable[[Assessment], StateType]
    attributes_fn: Callable[[Assessment], dict[str, Any]] | None = None
    enum_type: type[StrEnum] | None = None


SENSORS: tuple[SmartCompostSensorDescription, ...] = (
    SmartCompostSensorDescription(
        key="health",
        translation_key="health",
        value_fn=lambda assessment: assessment.health.score,
        attributes_fn=lambda assessment: {
            "provenance": assessment.health.provenance.value,
            "evaluable_domains": list(assessment.health.evaluable_domains),
            "domain_scores": {
                result.name: result.score
                for result in assessment.health.domains
            },
            "limitations": list(assessment.health.limitations),
            "diagnostics": [
                {
                    "code": item.code,
                    "confidence": item.confidence,
                    "signals": list(item.signals),
                }
                for item in assessment.diagnostics
            ],
        },
    ),
    SmartCompostSensorDescription(
        key="data_quality",
        translation_key="data_quality",
        value_fn=lambda assessment: assessment.data_quality,
    ),
    SmartCompostSensorDescription(
        key="confidence",
        translation_key="confidence",
        value_fn=lambda assessment: assessment.confidence,
    ),
    SmartCompostSensorDescription(
        key="priority_action",
        translation_key="priority_action",
        device_class=SensorDeviceClass.ENUM,
        enum_type=ActionCode,
        value_fn=lambda assessment: assessment.action.code.value,
        attributes_fn=lambda assessment: {
            "severity": assessment.action.severity.value,
            "reason_code": assessment.action.reason_code,
            "confidence": assessment.action.confidence,
        },
    ),
    SmartCompostSensorDescription(
        key="cycle_stage",
        translation_key="cycle_stage",
        device_class=SensorDeviceClass.ENUM,
        enum_type=CycleStage,
        value_fn=lambda assessment: assessment.cycle_stage.value,
    ),
    SmartCompostSensorDescription(
        key="phase",
        translation_key="phase",
        device_class=SensorDeviceClass.ENUM,
        enum_type=Phase,
        value_fn=lambda assessment: (
            assessment.phase.phase.value if assessment.phase.phase else None
        ),
        attributes_fn=lambda assessment: {
            "provenance": assessment.phase.provenance.value,
            "confidence": assessment.phase.confidence,
            "limitations": list(assessment.phase.limitations),
            "why": [
                {
                    "source": item.source,
                    "parameter": item.parameter,
                    "value": item.value,
                }
                for item in assessment.phase.evidence
            ],
            "trend": assessment.temperature_analysis.trend.value,
            "slope_per_hour": (
                round(assessment.temperature_analysis.slope_per_hour, 2)
                if assessment.temperature_analysis.slope_per_hour is not None
                else None
            ),
            "sample_count": assessment.temperature_analysis.sample_count,
            "peak_value": assessment.temperature_analysis.peak_value,
            "time_above_thermophilic_hours": _hours(
                assessment.temperature_analysis.time_above_thermophilic
            ),
            "time_above_hot_hours": _hours(
                assessment.temperature_analysis.time_above_hot
            ),
        },
    ),
    SmartCompostSensorDescription(
        key="cycle_report",
        translation_key="cycle_report",
        # The state is the report's identity (the cycle id), never a score:
        # no cycle at all renders as UNKNOWN, not as 0 (docs/04).
        value_fn=lambda assessment: (
            assessment.cycle_report.cycle_id
            if assessment.cycle_report is not None
            else None
        ),
        attributes_fn=_cycle_report_attributes,
    ),
    SmartCompostSensorDescription(
        key="maturity",
        translation_key="maturity",
        device_class=SensorDeviceClass.ENUM,
        enum_type=MaturityState,
        # "Ready for what?" — None renders as unknown, never as a guess
        # (docs/07 §9, docs/04).
        value_fn=lambda assessment: (
            assessment.maturity.state.value
            if assessment.maturity.state is not None
            else None
        ),
        attributes_fn=_maturity_attributes,
    ),
)


class SmartCompostSensor(CoordinatorEntity[SmartCompostCoordinator], SensorEntity):
    """A derived result entity for one compost bin."""

    _attr_has_entity_name = True
    entity_description: SmartCompostSensorDescription

    def __init__(
        self, runtime: BinRuntime, description: SmartCompostSensorDescription
    ) -> None:
        super().__init__(runtime.coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{runtime.bin_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.bin_id)},
            name=runtime.device_name,
            manufacturer="Smart Compost Manager",
            model=runtime.device_model,
        )
        if description.enum_type is not None:
            self._attr_options = [
                member.value for member in description.enum_type
            ]

    @property
    def native_value(self) -> StateType:
        """The derived value; None renders as `unknown`, never as 0."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartCompostConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the derived entities of one compost bin."""
    runtime = entry.runtime_data
    async_add_entities(
        SmartCompostSensor(runtime, description) for description in SENSORS
    )
