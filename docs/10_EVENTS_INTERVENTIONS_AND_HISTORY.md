# 10 — Events, Interventions and History

## 1. Perché gli eventi sono fondamentali

Il compost non è uno stato statico.

È una sequenza:

```text
material
→ biological response
→ intervention
→ new response
```

Per questo l'evento è una parte centrale del modello.

## 2. Event types

Almeno:

```text
material_added
watering
turning
aeration
manual_correction
observation
phase_changed
temperature_peak
rapid_heating
rapid_cooling
anomaly
health_changed
cycle_started
cycle_completed
maturity_estimated
```

## 3. Intervention types

```text
watering
turning
aeration
green_addition
brown_addition
correction
other
```

## 4. Event metadata

Ogni evento deve avere:

```text
timestamp
bin_id
cycle_id
type
source
notes
```

Quando utile:

```text
duration
before_state
after_state
reason
```

## 5. Manual vs automatic

L'origine deve distinguere:

```text
manual
automation
integration
```

## 6. Time since event

Il motore deve poter calcolare:

- time since last addition;
- time since turning;
- time since watering;
- time since last correction;
- time since cycle start.

## 7. Intervention verification

Per un intervento, definire una finestra di osservazione.

Esempio:

```text
Turning
→ observe temperature trend for next X hours
```

La finestra concreta è una decisione implementativa da testare.

## 8. Causal caution

La correlazione temporale non prova causalità.

Preferire:

> response appears positive after turning.

a:

> turning caused the temperature increase.

## 9. Timeline

La timeline deve essere leggibile.

Esempio:

```text
09:00 — Added food scraps
12:00 — Temperature rising
15:00 — Turning recorded
18:00 — Temperature +9 °C from pre-turning value
```

## 10. History granularity

Il sistema deve distinguere:

- raw measurements;
- aggregates;
- important events;
- cycle summaries.

Non tutto deve essere persistito allo stesso livello.

## 11. History utility

Lo storico serve a:

- diagnosticare;
- confrontare cicli;
- verificare interventi;
- apprendere baseline;
- migliorare forecast.

## 12. Data retention

La retention deve essere controllabile.

Non usare il database interno come deposito infinito di dati ad alta frequenza.
