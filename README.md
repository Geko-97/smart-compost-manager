# Smart Compost Manager

> **A Compost Coach for Home Assistant** — understand how your compost is doing, which phase it is in, *why*, what you should do, and whether the intervention helped.

Smart Compost Manager is a custom Home Assistant integration for one or more compost bins. It is not a wall of sensors: it interprets what is actually available, says clearly what it does not know, explains every conclusion, and suggests the single most useful next action — including **"Nothing to do."**

## Status

Early development, actively built milestone by milestone (see [docs/25_ROADMAP.md](docs/25_ROADMAP.md)):

- **Done:** foundation, config flow, per-bin isolation, zero-sensor assessment (data quality, confidence, priority action, cycle stage), manual logging services with persistence, health engine (balance, aeration, thermal, moisture), sensor binding through the options flow, temperature intelligence (bounded history, trends, phase inference, multi-signal diagnostics), events + notifications (bus events, built-in notifications with persistence/cooldown/deduplication/recovery), multi-bin batch intelligence (explicit cycles, per-cycle reports, comparison against your own previous cycle, personal baseline), maturity (readiness for curing / maturity / garden use with an explicit forecast window).
- **Next:** guide, forecasts, release readiness.

## Principles

- **Never invent data.** Every value carries provenance: `measured`, `user_provided`, `estimated`, `inferred`, `unknown`. Missing data stays `unknown` — it is never replaced with `0`, an average, or an ambient reading.
- **Useful with zero sensors.** You only log what you do by hand; adding Home Assistant sensors later unlocks new capabilities automatically.
- **No duplicate sensors.** Physical measurements are used from existing Home Assistant entities; this integration only creates *derived* entities.
- **Multi-bin is native.** One config entry per bin: sensors, materials, cycles, health and notifications can never leak between bins.

## Requirements

- Home Assistant **2026.9.0 or newer**
- No hardware required

## Installation

### HACS (custom repository)

1. In HACS, open **Integrations → ⋮ (menu) → Custom repositories**.
2. Repository: `https://github.com/Geko-97/smart-compost-manager`, category **Integration**.
3. Install **Smart Compost Manager** and restart Home Assistant.

### Manual

1. Copy `custom_components/smart_compost/` into `<config>/custom_components/` of your Home Assistant instance.
2. Restart Home Assistant.

## Usage

1. **Settings → Devices & services → Add integration → Smart Compost Manager**.
2. Step 1 — name, compost type, method (continuous or batch).
3. Step 2 — environment: location, shelter, rain and sun exposure. Defaults stay *unknown* on purpose.

Then log what happens at the bin, from **Developer tools → Actions**:

```yaml
service: smart_compost.log_material
data:
  device_id: <your compost bin device>
  material_type: food_scraps
  quantity: 2
  quantity_unit: bucket
```

Also available: `smart_compost.log_observation` (moisture, odor, pests, structure, appearance, activity) and `smart_compost.log_intervention` (watering, turning, aeration, corrections…).

**Batch cycles:** if you manage separate batches, open and close them explicitly — only one window can be open per bin:

```yaml
service: smart_compost.start_cycle
data:
  device_id: <your compost bin device>
  notes: autumn batch
```

```yaml
service: smart_compost.complete_cycle
data:
  device_id: <your compost bin device>
  output_quantity: 40
  output_unit: litre
  output_destination: raised_bed
```

Each cycle produces a **cycle report** counting only what happened inside its window (materials with their amounts per unit of measure, observations, interventions, temperature samples, peak, hours above 40 °C — an unmeasured fact stays `unknown` with an explicit limitation, never a plausible number). The report of the current cycle is compared with the **previous cycle of the same bin**, and from the third completed cycle onward a **personal baseline** appears: your own median duration and peak, with a confidence that grows with corroborating cycles (60 → 80 → 100). Comparison never crosses a bin boundary — bin A never learns from bin B.

**Maturity (ready for what?):** phase says what is happening, **maturity** says how ready your material is — and for curing, for use, or for the garden. A claim never comes from one variable: it combines the batch's own age and its quiet period with a thermal fact when a temperature sensor exists, so a zero-sensor bin honestly tops out at *ready for curing* with an explicit limitation. A **continuous** bin mixes material of different ages and therefore never gets a batch-sharp decision. The forecast is a **window with its own confidence** (e.g. *3–19 days, 39%*), never a date — and it is not a lab analysis.

**Events & notifications:** every logged action and every detected transition (new cycle, phase change, health band move, temperature peak, rapid heating/cooling) is published on the event bus as `smart_compost_event`, and every notification decision as `smart_compost_notification` — machine-readable payloads (`bin_id`, `type`, `source`, `before_state`, `after_state`, `reason`, `severity`, `confidence`, `action`) for your own automations. The integration *also* renders chosen categories as Home Assistant persistent notifications: enable or disable each category per bin in **Configure** (all on by default). Built-in notifications are protected by a 15-minute persistence window, a 6-hour per-category cooldown, deduplication and recovery pairing — a wobbling sensor never produces a notification storm, and a reload never replays old history.

**Sensors (optional):** open the integration's *Configure* dialog to bind an existing temperature/humidity entity. Smart Compost Manager only reads it — it never creates a copy — and treats it as unknown again when it goes stale or unavailable. A bound temperature sensor also builds a **bounded time series** (rate-limited, capped, 14-day window) that drives the temperature trend, the biological **phase** (mesophilic / thermophilic / cooling / curing), and multi-signal diagnostics such as *rapid heating* — every finding needs at least two independent signals, otherwise it stays `unknown`.

**Advanced signals (optional):** the same *Configure* dialog can also bind **VOC**, **NH₃** and **fill-level** sensors, and each one was added only with a defined diagnostic role: elevated VOC plus wetness or a falling temperature → *possible anaerobic activity*; elevated ammonia plus a green-heavy balance → *possible nitrogen excess*; a nearly full bin that is still being fed → *bin nearly full*. Unit discipline is strict: VOC and ammonia count only in concentration units (ppb, ppm, µg/m³) and fill only in percent — an index or unknown scale supports nothing, exactly like a stale reading. Each finding appears in the health entity's `diagnostics` attribute with its confidence and its *why*; they never fire notifications or events on their own (docs/16 keeps that list curated), and a lone high reading is an observation, never a diagnosis. CO₂, weight, pH and EC stay unbound on purpose: no robust role for them yet.

## Entities

| Entity | Meaning |
| --- | --- |
| `…_health` | How healthy the process looks (`unknown` until enough evidence exists) |
| `…_data_quality` | How complete, continuous and fresh your data is (0–100) |
| `…_confidence` | How well-supported the current conclusions are (0–100) |
| `…_priority_action` | The single next action, including *Nothing to do* |
| `…_cycle_stage` | Bookkeeping stage of the current cycle (new / active / resting / completed) |
| `…_phase` | Biological phase from the thermal history (`unknown` until the history supports one; trend, peak and dwell time as attributes) |
| `…_cycle_report` | Report of the active (or latest completed) cycle: counts, thermal facts, output, deltas against your previous cycle and your personal baseline as attributes (`unknown` before the first cycle) |
| `…_maturity` | How ready the material is (`ready_for_curing` / `likely_mature` / `likely_suitable_for_garden_use`, `unknown` without evidence); evidence, limitations and the forecast window as attributes |

Health, Confidence and Data Quality are deliberately **three different numbers**: a bin can look fine while you know very little about it.

## Development

```bash
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/python -m pytest
```

The domain core in `custom_components/smart_compost/core/` is pure Python and must never import Home Assistant — this is enforced by tests. Product specification lives in [`docs/`](docs/).

## License

MIT — see [LICENSE](LICENSE).
