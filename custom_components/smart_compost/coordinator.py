"""Event-driven coordinator for one compost bin (docs/02, docs/12).

One config entry = one bin = one coordinator: all data, history and
assessment of a bin live behind this object, so multi-bin isolation is a
property of the architecture, not of careful coding (docs/11).

There is no polling: the assessment is recomputed only when something
actually changes (a log service call, a reload), which keeps the engine
cheap from 1 bin to 10+.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bindings import InputKind, measurement_from_state, read_bindings
from .const import CONF_BIN_ID, DOMAIN
from .core.assessment import Assessment, BinData, assess
from .core.cycle import bounded_cycles
from .core.events import (
    CompostEvent,
    EventOrigin,
    bounded_events,
    cycle_completed_event,
    cycle_started_event,
    intervention_event,
    material_event,
    observation_event,
    transition_events,
)
from .core.model import (
    Capability,
    Cycle,
    CycleStatus,
    EnvironmentProfile,
    Intervention,
    MaterialAddition,
    NumericValue,
    Output,
    UserObservation,
)
from .core.notifications import (
    CategoryState,
    NotificationCategory,
    evaluate_notifications,
    pulses_from_events,
    state_conditions,
)
from .core.temperature import record_sample
from .notify import (
    async_fire_event,
    async_fire_notification,
    async_show_notification,
    read_notification_categories,
)
from .store import BinRecords, BinStore

_LOGGER = logging.getLogger(__name__)

#: Which BinData field each bound input feeds (M9).
_INPUT_FIELDS: dict[InputKind, str] = {
    InputKind.TEMPERATURE: "internal_temperature",
    InputKind.MOISTURE: "internal_moisture",
    InputKind.VOC: "voc",
    InputKind.AMMONIA: "ammonia",
    InputKind.FILL: "fill_level",
}


def _capabilities(
    *,
    temperature: NumericValue | None,
    moisture: NumericValue | None,
    voc: NumericValue | None,
    ammonia: NumericValue | None,
    fill: NumericValue | None,
) -> frozenset[Capability]:
    """Capabilities ⇔ at least one fresh usable value (docs/04 ladder).

    VOC and ammonia share GAS_SIGNALS: the capability exists while EITHER
    sensor reports, so one going stale never silences the other.
    """
    capabilities = {Capability.MANUAL_DATA}
    if temperature is not None:
        capabilities.add(Capability.INTERNAL_TEMPERATURE)
    if moisture is not None:
        capabilities.add(Capability.INTERNAL_MOISTURE)
    if voc is not None or ammonia is not None:
        capabilities.add(Capability.GAS_SIGNALS)
    if fill is not None:
        capabilities.add(Capability.WEIGHT_FILL)
    return frozenset(capabilities)


@dataclass(slots=True)
class BinRuntime:
    """Runtime data for a single compost bin (one config entry = one bin).

    The isolation unit of the product (docs/11_MULTI_BIN_AND_CYCLES.md):
    nothing here is shared with another bin.
    """

    bin_id: str
    device_name: str
    device_model: str
    coordinator: SmartCompostCoordinator


type SmartCompostConfigEntry = ConfigEntry[BinRuntime]


class SmartCompostCoordinator(DataUpdateCoordinator[Assessment]):
    """Owns one bin's data and recomputes its assessment on every change."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SmartCompostConfigEntry,
        environment: EnvironmentProfile,
        records: BinRecords,
        store: BinStore,
    ) -> None:
        self._store = store
        self._entry = entry
        self._bin_id: str = entry.data[CONF_BIN_ID]
        self._bindings = read_bindings(entry.options)
        self._enabled_categories: frozenset[NotificationCategory] = (
            read_notification_categories(entry.options)
        )

        # M6 runtime history: everything persisted lives here too, so the
        # reload path reconstructs it 1:1 (PR-027: no loss, no duplicate).
        self._events: tuple[CompostEvent, ...] = records.events
        self._notify_states: dict[str, CategoryState] = dict(
            records.notification_states
        )
        self._last_assessment: Assessment | None = None
        self._last_data: BinData | None = None

        # Initial snapshot of the bound sensors: only fresh, numeric states
        # become capabilities — anything else stays UNKNOWN (docs/04).
        now = datetime.now(UTC)
        readings: dict[InputKind, NumericValue | None] = {
            kind: measurement_from_state(hass.states.get(entity_id), now)
            for entity_id, kind in self._bindings.items()
        }
        temperature = readings.get(InputKind.TEMPERATURE)
        moisture = readings.get(InputKind.MOISTURE)
        voc = readings.get(InputKind.VOC)
        ammonia = readings.get(InputKind.AMMONIA)
        fill = readings.get(InputKind.FILL)

        capabilities = _capabilities(
            temperature=temperature,
            moisture=moisture,
            voc=voc,
            ammonia=ammonia,
            fill=fill,
        )

        # The first fresh reading is history too (docs/10); it is persisted
        # together with the next saved record — no store write in here.
        history = records.temperature
        if temperature is not None:
            history = record_sample(history, temperature)

        self.bin_data = BinData(
            environment=environment,
            capabilities=capabilities,
            internal_temperature=temperature,
            internal_moisture=moisture,
            voc=voc,
            ammonia=ammonia,
            fill_level=fill,
            temperature_history=history,
            material_additions=records.materials,
            observations=records.observations,
            interventions=records.interventions,
            cycles=records.cycles,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            # Maturity and staleness depend on the CLOCK, not only on new
            # events (docs/02: periodic evaluation). One quiet re-assessment
            # per hour keeps those conclusions current without polling any
            # sensor (docs/12 §4: no useless polling); every sensor event
            # still re-assesses immediately.
            update_interval=timedelta(hours=1),
        )
        if self._bindings:
            # Event-driven: the assessment follows the sensors without any
            # polling (docs/23 performance plan).
            entry.async_on_unload(
                async_track_state_change_event(
                    hass, list(self._bindings), self.async_on_state_change
                )
            )

    async def async_on_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Re-assess the bin when a bound sensor reports a new state."""
        new_state: State | None = event.data.get("new_state")
        now = datetime.now(UTC)
        value = measurement_from_state(new_state, now)
        kind = self._bindings.get(event.data["entity_id"])
        if kind is None:
            return

        # A temperature reading extends the time series (docs/10): the
        # sample is rate-limited and bounded inside core, then persisted
        # BEFORE it is published (a failed write never fakes a success).
        history = self.bin_data.temperature_history
        if kind is InputKind.TEMPERATURE and value is not None:
            updated = record_sample(history, value)
            if updated is not history:
                await self._store.async_save(
                    replace(self._current_records(), temperature=updated)
                )
                history = updated

        self.bin_data = replace(
            self._with_measurement(kind, value),
            temperature_history=history,
        )
        self.async_set_updated_data(await self._async_update_data())

    def _with_measurement(
        self, kind: InputKind, value: NumericValue | None
    ) -> BinData:
        """Apply a reading and keep capability ⇔ usable value in lockstep.

        Capabilities are recomputed from EVERY reading (M9): VOC and
        ammonia share one capability, so a stale VOC sensor must not drop
        the ammonia that is still reporting.
        """
        updated = replace(self.bin_data, **{_INPUT_FIELDS[kind]: value})
        return replace(
            updated,
            capabilities=_capabilities(
                temperature=updated.internal_temperature,
                moisture=updated.internal_moisture,
                voc=updated.voc,
                ammonia=updated.ammonia,
                fill=updated.fill_level,
            ),
        )

    async def _async_update_data(self) -> Assessment:
        """Recompute the assessment, detect transitions and notify.

        Persist first, then fire: a failed write never fakes a published
        event (docs/19). The first run has no previous assessment — it is
        a baseline, so a reload never replays old transitions (PR-027).
        """
        now = datetime.now(UTC)
        assessment = assess(self.bin_data, now)

        events = transition_events(
            self._last_assessment, assessment, now, self._bin_id
        )
        pulses = pulses_from_events(events, assessment)
        conditions = state_conditions(self._last_data, self.bin_data, assessment)
        sent, states = evaluate_notifications(
            pulses, conditions, self._notify_states, now
        )

        if events:
            self._events = bounded_events(self._events + events)
        changed = bool(events) or states != self._notify_states
        self._notify_states = states
        if changed:
            await self._store.async_save(self._current_records())

        self._last_assessment = assessment
        self._last_data = self.bin_data

        for event in events:
            async_fire_event(self.hass, event)
        for note in sent:
            async_fire_notification(self.hass, self._bin_id, note)
            await async_show_notification(
                self.hass, self._entry, note, self._enabled_categories
            )
        return assessment

    async def async_log_material(self, record: MaterialAddition) -> None:
        """Append a material addition and re-assess the bin."""
        event = material_event(
            record.timestamp, record.material_type, record.notes, self._bin_id
        )
        self._events = bounded_events(self._events + (event,))
        await self._async_commit(
            replace(
                self._current_records(),
                materials=self.bin_data.material_additions + (record,),
            ),
            fired=event,
        )

    async def async_log_observation(self, record: UserObservation) -> None:
        """Append an observation and re-assess the bin."""
        event = observation_event(
            record.timestamp,
            record.category.value,
            record.value,
            record.notes,
            self._bin_id,
        )
        self._events = bounded_events(self._events + (event,))
        await self._async_commit(
            replace(
                self._current_records(),
                observations=self.bin_data.observations + (record,),
            ),
            fired=event,
        )

    async def async_log_intervention(self, record: Intervention) -> None:
        """Append an intervention and re-assess the bin."""
        event = intervention_event(
            record.timestamp, record.type.value, record.notes, self._bin_id
        )
        self._events = bounded_events(self._events + (event,))
        await self._async_commit(
            replace(
                self._current_records(),
                interventions=self.bin_data.interventions + (record,),
            ),
            fired=event,
        )

    def _current_records(self) -> BinRecords:
        """Snapshot of every persisted history of this bin."""
        return BinRecords(
            materials=self.bin_data.material_additions,
            observations=self.bin_data.observations,
            interventions=self.bin_data.interventions,
            temperature=self.bin_data.temperature_history,
            cycles=self.bin_data.cycles,
            events=self._events,
            notification_states=tuple(sorted(self._notify_states.items())),
        )

    async def _async_commit(
        self, records: BinRecords, fired: CompostEvent | None = None
    ) -> None:
        """Persist first, then publish: a failed write never fakes a success."""
        await self._store.async_save(records)
        self.bin_data = replace(
            self.bin_data,
            material_additions=records.materials,
            observations=records.observations,
            interventions=records.interventions,
            temperature_history=records.temperature,
            cycles=records.cycles,
        )
        if fired is not None:
            async_fire_event(self.hass, fired)
        self.async_set_updated_data(await self._async_update_data())

    async def async_start_cycle(self, notes: str | None = None) -> Cycle:
        """Start an explicit batch cycle for this bin (M7, docs/11 §6).

        Only one cycle can be active at a time: starting a second one would
        make the report window ambiguous, so the call fails loudly instead
        of silently picking a winner.
        """
        if self._active_cycle() is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cycle_already_active",
                translation_placeholders={"bin_id": self._bin_id},
            )
        now = datetime.now(UTC)
        cycle = Cycle(id=uuid4().hex, started_at=now)
        event = cycle_started_event(now, self._bin_id, cycle.id, EventOrigin.MANUAL)
        if notes:
            event = replace(event, notes=notes)
        self._events = bounded_events(self._events + (event,))
        await self._async_commit(
            replace(
                self._current_records(),
                cycles=bounded_cycles(self.bin_data.cycles + (cycle,)),
            ),
            fired=event,
        )
        return cycle

    async def async_complete_cycle(self, output: Output | None = None) -> Cycle:
        """Complete the active cycle, optionally with an output report.

        Without an active cycle there is nothing to complete: the error is
        explicit rather than a fabricated completion (docs/04).
        """
        active = self._active_cycle()
        if active is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_cycle",
                translation_placeholders={"bin_id": self._bin_id},
            )
        now = datetime.now(UTC)
        completed = replace(
            active,
            status=CycleStatus.COMPLETED,
            completed_at=now,
            output=output,
        )
        event = cycle_completed_event(
            now, self._bin_id, completed.id, EventOrigin.MANUAL,
            has_output=output is not None,
        )
        self._events = bounded_events(self._events + (event,))
        await self._async_commit(
            replace(
                self._current_records(),
                cycles=bounded_cycles(
                    tuple(
                        completed if item.id == active.id else item
                        for item in self.bin_data.cycles
                    )
                ),
            ),
            fired=event,
        )
        return completed

    def _active_cycle(self) -> Cycle | None:
        """The cycle currently open for this bin, if any (this bin only)."""
        return next(
            (
                cycle
                for cycle in self.bin_data.cycles
                if cycle.status is CycleStatus.ACTIVE
            ),
            None,
        )
