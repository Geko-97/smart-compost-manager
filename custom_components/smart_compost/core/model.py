"""Domain model for Smart Compost Manager.

Pure Python: modules in the `core` package must never import Home Assistant.
Every quantity carries its provenance explicitly; UNKNOWN is a valid,
first-class state that must never be replaced by a plausible number
(docs/04_DATA_PROVENANCE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Provenance(StrEnum):
    """Where a value or a conclusion comes from (docs/04_DATA_PROVENANCE.md)."""

    MEASURED = "measured"
    USER_PROVIDED = "user_provided"
    ESTIMATED = "estimated"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class QuantityPrecision(StrEnum):
    """How precise a user-provided quantity is."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    QUALITATIVE = "qualitative"


# --- Bin configuration -------------------------------------------------------


class CompostType(StrEnum):
    """Kind of container or pile (docs/11: bin types)."""

    ENCLOSED_BIN = "enclosed_bin"
    TUMBLER = "tumbler"
    OPEN_PILE = "open_pile"
    GARDEN_COMPOST = "garden_compost"
    OTHER = "other"


class CompostMethod(StrEnum):
    """How the bin is managed (docs/11: continuous vs batch)."""

    CONTINUOUS = "continuous"
    BATCH = "batch"


class Location(StrEnum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    UNKNOWN = "unknown"


class Shelter(StrEnum):
    SHELTERED = "sheltered"
    SEMI_SHELTERED = "semi_sheltered"
    EXPOSED = "exposed"
    UNKNOWN = "unknown"


class RainExposure(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    EXPOSED = "exposed"
    UNKNOWN = "unknown"


class SunExposure(StrEnum):
    SHADE = "shade"
    PARTIAL = "partial"
    FULL_SUN = "full_sun"
    UNKNOWN = "unknown"


# --- Cycle and decision vocabulary ------------------------------------------


class CycleStage(StrEnum):
    """Bookkeeping stage of the current cycle (docs/07, docs/11).

    Deliberately separate from the biological phase: the stage is known from
    user history alone, the phase requires measurements.
    """

    NEW = "new"
    ACTIVE = "active"
    RESTING = "resting"
    COMPLETED = "completed"


class Phase(StrEnum):
    """Biological phase from thermal history (docs/07).

    Deliberately separate from CycleStage: the stage is bookkeeping, the
    phase is a trajectory — and without enough history it stays unknown.
    """

    MESOPHILIC = "mesophilic"
    THERMOPHILIC = "thermophilic"
    COOLING = "cooling"
    CURING = "curing"


class MaturityState(StrEnum):
    """How ready the material is — FOR WHAT (docs/07 §9).

    Deliberately separate from Phase: the phase says what is happening in
    the process, maturity says how ready the material probably is for a
    use. `None` (rendered as unknown) is the honest answer without enough
    evidence — there is no "kind of ready" member, because a half-truth in
    a readiness claim is a lie (docs/01 PR-015).
    """

    READY_FOR_CURING = "ready_for_curing"
    LIKELY_MATURE = "likely_mature"
    LIKELY_SUITABLE_FOR_GARDEN_USE = "likely_suitable_for_garden_use"


class ActionCode(StrEnum):
    """Machine-readable recommended actions (translated in the UI)."""

    NONE = "none"
    LOG_FIRST_ADDITION = "log_first_addition"
    ADD_BROWNS = "add_browns"
    ADD_GREENS = "add_greens"
    IMPROVE_AERATION = "improve_aeration"
    WATER_COMPOST = "water_compost"


class Severity(StrEnum):
    INFO = "info"
    SUGGESTION = "suggestion"
    RECOMMENDED = "recommended"
    URGENT = "urgent"


# --- User-provided records ---------------------------------------------------


class ObservationCategory(StrEnum):
    """Simple observation vocabulary (docs/10)."""

    MOISTURE = "moisture"
    ODOR = "odor"
    PESTS = "pests"
    STRUCTURE = "structure"
    APPEARANCE = "appearance"
    ACTIVITY = "activity"


class InterventionType(StrEnum):
    """User interventions (docs/10)."""

    WATERING = "watering"
    TURNING = "turning"
    AERATION = "aeration"
    GREEN_ADDITION = "green_addition"
    BROWN_ADDITION = "brown_addition"
    CORRECTION = "correction"
    OTHER = "other"


class CycleStatus(StrEnum):
    """Lifecycle of one batch cycle (docs/11 §6).

    ARCHIVED arrives with the archive/reset milestone; until then a
    completed cycle simply stays completed.
    """

    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class EnvironmentProfile:
    """Static environment of a bin.

    Defaults are UNKNOWN on purpose: a missing configuration value is unknown,
    never a guessed value.

    `method` is None when the user never told us how the bin is managed:
    CompostMethod has no UNKNOWN member on purpose (it is a user-facing
    choice), so "not configured" stays None instead of pretending one.
    """

    location: Location = Location.UNKNOWN
    shelter: Shelter = Shelter.UNKNOWN
    rain_exposure: RainExposure = RainExposure.UNKNOWN
    sun_exposure: SunExposure = SunExposure.UNKNOWN
    method: CompostMethod | None = None


@dataclass(frozen=True, slots=True)
class MaterialAddition:
    """A logged material addition. Record-level provenance is USER_PROVIDED."""

    timestamp: datetime
    material_type: str
    quantity_value: float | None
    quantity_unit: str | None
    quantity_precision: QuantityPrecision
    provenance: Provenance = Provenance.USER_PROVIDED
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UserObservation:
    """A user observation. Record-level provenance is USER_PROVIDED."""

    timestamp: datetime
    category: ObservationCategory
    value: str
    severity: Severity = Severity.INFO
    provenance: Provenance = Provenance.USER_PROVIDED
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class Intervention:
    """A user intervention. Record-level provenance is USER_PROVIDED."""

    timestamp: datetime
    type: InterventionType
    duration_minutes: int | None = None
    provenance: Provenance = Provenance.USER_PROVIDED
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class Output:
    """What a completed cycle produced (docs/11 §10).

    Every field is optional because the user may report any subset — an
    unmeasured output stays None, never 0 (docs/04).
    """

    timestamp: datetime
    quantity_value: float | None = None
    quantity_unit: str | None = None
    destination: str | None = None
    notes: str | None = None
    provenance: Provenance = Provenance.USER_PROVIDED


@dataclass(frozen=True, slots=True)
class Cycle:
    """One batch cycle of one bin (docs/11 §6): start, feed, complete.

    Cycles are created explicitly by the user — a continuous bin without
    batch tracking honestly has none (docs/11 §5, §9).
    """

    id: str
    started_at: datetime
    status: CycleStatus = CycleStatus.ACTIVE
    completed_at: datetime | None = None
    output: Output | None = None


# --- Physical quantities -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class NumericValue:
    """A numeric quantity that always carries its provenance.

    Invariants enforced at construction (docs/04):
    * a missing value must be UNKNOWN — never 0, never an average;
    * UNKNOWN never carries a number;
    * MEASURED requires a timestamp (no timeless "measurements").
    """

    value: float | None
    unit: str | None
    provenance: Provenance
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.value is None and self.provenance is not Provenance.UNKNOWN:
            raise ValueError("a missing value must carry provenance UNKNOWN")
        if self.provenance is Provenance.UNKNOWN and self.value is not None:
            raise ValueError("UNKNOWN provenance cannot carry a value")
        if self.provenance is Provenance.MEASURED and self.timestamp is None:
            raise ValueError("measured values require a timestamp")

    @classmethod
    def unknown(cls, unit: str | None = None) -> NumericValue:
        """The honest representation of a missing measurement."""
        return cls(value=None, unit=unit, provenance=Provenance.UNKNOWN)


# --- Capabilities ------------------------------------------------------------


class Capability(StrEnum):
    """Progressive capabilities of a bin (docs/04, "capability ladder").

    A capability is present only when the underlying data is really available
    (bound and fresh); its absence is what keeps conclusions honest.
    """

    MANUAL_DATA = "manual_data"
    INTERNAL_TEMPERATURE = "internal_temperature"
    AMBIENT_TEMPERATURE = "ambient_temperature"
    INTERNAL_MOISTURE = "internal_moisture"
    WEATHER = "weather"
    GAS_SIGNALS = "gas_signals"
    WEIGHT_FILL = "weight_fill"


def enum_or_unknown[T: StrEnum](enum_cls: type[T], raw: object) -> T:
    """Interpret a stored raw value as `enum_cls`, falling back to UNKNOWN.

    Every enum passed here must define an UNKNOWN member. UNKNOWN is the
    honest fallback for anything missing or uninterpretable: a corrupted
    stored setting must never be presented as a real value.
    """
    if isinstance(raw, enum_cls):
        return raw
    if isinstance(raw, str):
        try:
            return enum_cls(raw)
        except ValueError:
            pass
    return enum_cls.UNKNOWN


# --- Input container ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BinData:
    """Everything the engine knows about one bin.

    One instance per config entry: there is no shared or global state, which
    is how multi-bin isolation is guaranteed (docs/11).
    """

    environment: EnvironmentProfile = EnvironmentProfile()
    capabilities: frozenset[Capability] = frozenset()
    internal_temperature: NumericValue | None = None
    internal_moisture: NumericValue | None = None
    #: Advanced signals (M9): present only while their binding is fresh.
    voc: NumericValue | None = None
    ammonia: NumericValue | None = None
    fill_level: NumericValue | None = None
    temperature_history: tuple[NumericValue, ...] = ()
    material_additions: tuple[MaterialAddition, ...] = ()
    observations: tuple[UserObservation, ...] = ()
    interventions: tuple[Intervention, ...] = ()
    cycles: tuple[Cycle, ...] = ()
