"""Named tuning constants for the assessment engine.

Every weight and threshold lives here, named and documented
(docs/24_CODING_RULES.md, "magic numbers"). The test suite hand-computes the
expected outputs from these constants so a silent weight change cannot slip
through unnoticed.
"""

from __future__ import annotations

from datetime import timedelta

# --- Data quality (docs/06): completeness x continuity x freshness -----------

#: Physical signals that would make a bin "measurably observed" at minimum:
#: internal temperature and internal moisture. Ambient values do not count —
#: they are not the compost (docs/11 gap analysis).
BASELINE_MEASURABLE_SIGNALS = 2

DQ_MEASUREMENT_WEIGHT = 0.5
DQ_USER_DATA_WEIGHT = 0.3
DQ_FRESHNESS_WEIGHT = 0.2

#: Shares of the "user provides data" score (sum to 1.0).
DQ_MATERIAL_SHARE = 0.5
DQ_OBSERVATION_SHARE = 0.3
DQ_INTERVENTION_SHARE = 0.2

#: Freshness windows used by both data quality and evidence recency.
FRESH_WINDOW = timedelta(days=7)
STALE_WINDOW = timedelta(days=30)

# --- Confidence (docs/06): evidence domains x recency ------------------------

#: Decision domains that will eventually feed conclusions (thermal, moisture,
#: aeration, balance, activity, progress). M1 evaluates none of them, so
#: confidence starts low — honestly.
TOTAL_DECISION_DOMAINS = 6

#: Beyond this many pieces of evidence, support is considered saturated.
MAX_COUNTED_EVIDENCE = 3

WEIGHT_DOMAIN_COVERAGE = 0.5
WEIGHT_EVIDENCE_SUPPORT = 0.5

# --- Health domains (M3) -----------------------------------------------------

#: Window for evaluating health domains from user-logged data.
HEALTH_WINDOW = timedelta(days=14)

#: Minimum classified materials before the balance domain can be evaluated.
#: Below this, the domain stays UNKNOWN instead of guessing from too little.
BALANCE_MIN_MATERIALS = 3

#: Balance scores (docs/08): all-green risks sourness, all-brown dries out.
BALANCE_ALL_GREEN_SCORE = 40
BALANCE_ALL_BROWN_SCORE = 55
BALANCE_MIXED_SCORE = 85

#: Aeration scores from user-observed signals (docs/12): odors and
#: compaction point at possible poor aeration; absence of complaints does
#: NOT prove good aeration (that stays UNKNOWN).
AERATION_ONE_ADVERSE_SCORE = 45
AERATION_MULTIPLE_ADVERSE_SCORE = 25
AERATION_POSITIVE_ONLY_SCORE = 85

#: Below this aeration score, improving aeration becomes the priority action.
AERATION_ACTION_THRESHOLD = 50

# --- Sensor measurements (M4) ------------------------------------------------

#: A bound sensor is consumed only while its state is fresher than this;
#: afterwards the capability (and the domain that depends on it) drops back
#: to UNKNOWN — stale data is never presented as current (docs/04).
SENSOR_STALE_AFTER = timedelta(minutes=30)

#: Thermal health bands as (upper bound exclusive, score, reason).
#: These describe the CURRENT state only: trends, rates and heating events
#: need history and land in a later milestone (docs/10).
THERMAL_BANDS: tuple[tuple[float, int, str], ...] = (
    (5.0, 35, "dormant"),
    (15.0, 50, "very_slow"),
    (25.0, 65, "slow"),
    (40.0, 80, "active"),
    (65.0, 90, "thermophilic"),
    (75.0, 70, "hot"),
    (float("inf"), 45, "overheating"),
)

#: Internal moisture bands as (upper bound exclusive, score, reason).
#: 40–60% is the classic ideal range for compost (docs/06, docs/11).
MOISTURE_BANDS: tuple[tuple[float, int, str], ...] = (
    (20.0, 25, "too_dry"),
    (30.0, 40, "too_dry"),
    (40.0, 70, "dry_side"),
    (60.0, 90, "ideal"),
    (70.0, 70, "wet_side"),
    (80.0, 40, "too_wet"),
    (float("inf"), 25, "too_wet"),
)

# --- Temperature history (M5, docs/10) --------------------------------------

#: A new sample is stored when this much time passed...
SAMPLE_MIN_INTERVAL = timedelta(minutes=5)
#: ...or when the value moved significantly (a real jump is always worth
#: keeping, it is what peak and heating detection feed on).
SAMPLE_SIGNIFICANT_DELTA = 2.0

#: History window and hard cap (memory stays bounded from 1 to 10+ bins).
TEMPERATURE_HISTORY_WINDOW = timedelta(days=14)
MAX_TEMPERATURE_SAMPLES = 1000

#: A trend needs this much evidence before it may be claimed (docs/06:
#: insufficient evidence → UNKNOWN, not a guess).
TREND_MIN_SAMPLES = 6
TREND_MIN_SPAN = timedelta(minutes=60)

#: Slopes inside this deadband count as "stable" (hysteresis against noise).
SLOPE_STABLE_DEADBAND = 0.3  # °C per hour

#: Dwell-time thresholds (docs/10: time above thresholds).
TIME_ABOVE_THERMOPHILIC = 40.0  # °C
TIME_ABOVE_HOT = 70.0  # °C

#: A fast rise at high temperature caps the thermal health score (the only
#: time-series-driven health signal in M5).
THERMAL_FAST_RISE = 1.0  # °C per hour
THERMAL_FAST_RISE_SCORE_CAP = 55

# --- Phase detection (M5, docs/07) ------------------------------------------

PHASE_THERMOPHILIC_CURRENT = 40.0  # °C
PHASE_PEAK_SIGNIFICANT = 45.0  # °C
PHASE_PEAK_RECENT = timedelta(hours=72)
PHASE_COOLING_DROP = 5.0  # °C below the window peak
PHASE_COOLING_MAX_CURRENT = 35.0  # °C
PHASE_CURE_WINDOW = timedelta(days=5)
PHASE_CURE_MIN_SAMPLES = 3
PHASE_CURE_MIN = 15.0  # °C
PHASE_CURE_MAX = 30.0  # °C
PHASE_CURE_RANGE = 5.0  # °C
PHASE_MESOPHILIC_MIN = 15.0  # °C
PHASE_MESOPHILIC_MAX = 40.0  # °C

#: A phase is a trajectory, never a point: at least two history samples
#: are needed before any phase may be claimed (docs/07).
PHASE_MIN_SAMPLES = 2

#: Thermophilic evidence must show DURATION above the threshold, not a
#: momentary excursion (docs/07 §6: duration, not the calendar).
PHASE_THERMOPHILIC_MIN_DWELL = timedelta(hours=3)

# --- Multi-signal diagnostics (M5, docs/06) ---------------------------------

#: A finding requires at least two independent signals; confidence grows
#: with corroboration, never with repetition.
DIAGNOSTIC_CONFIDENCE_2_SIGNALS = 70
DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS = 85

#: A recent material addition counts as corroborating signal only within
#: this window ("it was fueled recently", not "it was fueled once").
DIAGNOSTIC_RECENT_FUELING = timedelta(hours=24)

# --- Events (M6, docs/10) ---------------------------------------------------

#: Stored events stay bounded: the newest MAX_STORED_EVENTS survive, older
#: ones age out (docs/19 §10: conservative but not unbounded retention).
MAX_STORED_EVENTS = 200

#: A temperature_peak event needs a NEW significant peak: the window peak
#: crosses PHASE_PEAK_SIGNIFICANT from below and rises at least this much,
#: so a steady heat-up reports once instead of on every sample (docs/16 §7).
EVENT_PEAK_MIN_RISE = 1.0  # °C

#: Health bands for change events. Score movement INSIDE a band is noise,
#: never an event: an oscillating sensor must not flap (docs/16 §7).
HEALTH_BAND_POOR_MAX = 40.0  # below → "poor"
HEALTH_BAND_FAIR_MAX = 70.0  # 40–69 → "fair", 70+ → "good"

# --- Notifications (M6, docs/16) -------------------------------------------

#: A state condition must persist this long before anything is notified;
#: anything shorter is noise and vanishes silently — no issue/recovered
#: ping-pong from a sensor wobble (docs/16 §7).
NOTIFY_PERSISTENCE = timedelta(minutes=15)

#: Minimum silence between two notifications of the SAME category, counted
#: from the last send (issue or recovery): the anti-spam guarantee, and it
#: survives restarts because it is persisted (docs/26 §6).
NOTIFY_COOLDOWN = timedelta(hours=6)

# --- Cycles, comparison and baselines (M7, docs/11, docs/18) ---------------

#: Stored cycles stay bounded; the oldest completed cycles age out first
#: (an active cycle is never dropped — docs/19 §10 retention).
MAX_STORED_CYCLES = 50

#: A personal baseline needs this many COMPLETED cycles before it exists
#: at all (docs/18 §4: no baseline after a couple of observations).
BASELINE_MIN_CYCLES = 3

#: Confidence of a baseline grows with corroborating cycles and saturates:
#: min(completed, MAX) * STEP → 60 / 80 / 100 (docs/18 §6).
BASELINE_MAX_CYCLES = 5
BASELINE_CONFIDENCE_STEP = 20

# --- Maturity (M8, docs/07 §8–§13, docs/18) ---------------------------------

#: Maturity is never declared from a single variable (docs/01 PR-015): a
#: readiness claim needs at least two INDEPENDENT signals — time alone plus
#: a thermal fact, never a lone calendar reading.
MATURITY_MIN_SIGNALS = 2

#: "Enough time" before any readiness state, "quiet" before garden use is
#: suggested (no fresh addition in the meantime), and the stronger window
#: a batch must reach before `likely_suitable_for_garden_use` (docs/07 §8).
MATURITY_MIN_ELAPSED = timedelta(days=7)
MATURITY_QUIET = timedelta(days=7)
MATURITY_GARDEN_MIN_ELAPSED = timedelta(days=21)

#: Confidence by number of corroborating signals (never by repetition).
MATURITY_CONFIDENCE_2_SIGNALS = 55
MATURITY_CONFIDENCE_3_SIGNALS = 70
MATURITY_CONFIDENCE_4_PLUS_SIGNALS = 85

#: A continuous bin mixes material of different ages: the whole-container
#: claim can never be batch-sharp (docs/07 §10), so the state is capped at
#: the weakest readiness and the confidence with it.
MATURITY_CONTINUOUS_CONFIDENCE_CAP = 40

# --- Advanced signals (M9, docs/00 §6, docs/14 §7, docs/05) -----------------

#: Elevated total VOC, BY UNIT. Concentration units only: an index, a
#: percentage or an unknown unit says nothing about concentration and
#: therefore supports no claim at all (docs/04: unknown stays unknown).
#: 1000 ppb is the commonly used "elevated" indoor TVOC level.
VOC_ELEVATED: dict[str, float] = {
    "ppb": 1000.0,
    "ppm": 1.0,
    "µg/m³": 4000.0,
    "ug/m³": 4000.0,
}

#: Odour-level ammonia: pungent readings indicate nitrogen escaping from
#: the pile. Same unit discipline as VOC (docs/04).
AMMONIA_ELEVATED: dict[str, float] = {
    "ppb": 5000.0,
    "ppm": 5.0,
    "µg/m³": 3500.0,
    "ug/m³": 3500.0,
}

#: Fill is only read as a percentage of capacity — an absolute volume or
#: an unknown scale cannot say how full the bin is.
FILL_UNIT = "%"
FILL_NEARLY_FULL = 85.0

#: The forecast is a WINDOW, never a date (docs/07 §12). Without a personal
#: baseline the window is wider and its confidence degrades (docs/18 §6–§7).
MATURITY_FORECAST_GENERIC_SPREAD = 8  # days around the target
MATURITY_FORECAST_BASELINE_SPREAD = 4  # days around the personal median
MATURITY_FORECAST_MIN_SPAN = 4  # a window is never narrower than this
MATURITY_FORECAST_GENERIC_CONFIDENCE = 70  # % of the claim's confidence
