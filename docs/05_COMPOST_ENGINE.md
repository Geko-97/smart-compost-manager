# 05 — Compost Engine

## 1. Obiettivo

Il motore interpreta il comportamento del compost sulla base delle evidenze disponibili.

Non è necessario implementare un modello biologico perfetto. È invece necessario costruire un modello:

- coerente;
- prudente;
- spiegabile;
- testabile;
- estendibile.

## 2. Input

- measurements;
- observations;
- materials;
- interventions;
- cycle;
- environment;
- weather;
- historical aggregates.

## 3. Output

- current state;
- activity;
- phase;
- health;
- maturity;
- diagnostics;
- recommendation;
- forecast;
- confidence;
- data quality.

## 4. Feature extraction

### Temperature features

- current;
- min;
- max;
- trend;
- rate of rise;
- rate of fall;
- delta vs ambient;
- duration above important thresholds;
- peak count;
- peak magnitude;
- peak duration;
- recovery after intervention.

### Moisture features

- current if measured;
- trend;
- persistence above/below target band;
- recent rain;
- recent watering;
- relation to temperature;
- relation to material additions.

### Material features

- recent green mass;
- recent brown mass;
- material diversity;
- structural contribution;
- approximate moisture contribution;
- decomposition speed;
- problematicness.

### Temporal features

- age of cycle;
- time since last addition;
- time since turning;
- time since watering;
- time since last observation;
- time since anomaly.

## 5. Persistence

Un singolo sample anomalo non deve generare un problema grave.

Per stati significativi usare almeno uno dei seguenti concetti:

- number of consecutive samples;
- duration;
- rolling window;
- hysteresis;
- repeated evidence.

Cursor è libero di scegliere l'implementazione più adatta.

## 6. State machine vs scoring

La phase detection può usare una state machine, scoring o combinazione dei due.

Vincolo:

> il risultato deve evitare oscillazioni irrealistiche tra fasi.

## 7. Health engine

Health deve essere composto da componenti interpretabili.

Esempio concettuale:

```text
thermal
moisture
aeration
balance
activity
progress
```

Una componente non valutabile non deve essere trattata automaticamente come "neutra".

## 8. Diagnostic engine

La diagnostica deve cercare correlazioni.

Esempio:

```text
high internal moisture
+
falling temperature
+
elevated VOC
+
recent rain
```

può supportare:

> possible excessive moisture / poor aeration.

Non dimostra da sola una specifica condizione microbiologica.

## 9. Recommendation engine

Regola:

> scegliere l'azione minima ragionevole supportata dalle evidenze.

Possibili azioni:

- no action;
- monitor;
- turn/aerate;
- add dry brown;
- add moisture;
- reduce new wet green input;
- check structure;
- inspect for pests.

## 10. Intervention verification

Dopo l'intervento il motore deve poter confrontare:

```text
before
→ intervention
→ after
```

e produrre:

> appears effective

con confidence.

## 11. Forecast

Il forecast deve essere un livello superiore rispetto allo stato attuale.

Esempi:

- expected maturation window;
- drying risk;
- rain risk;
- likely slowdown;
- likely next temperature trend.

## 12. No-action is first-class

La funzione principale non deve sempre generare una raccomandazione.

Può restituire:

```text
action = NONE
```

con messaggio:

> No action needed.

## 13. Future model providers

La prima versione può essere rule/statistics based.

In futuro:

```text
RuleModel
StatisticalModel
MLModel
```

possono condividere la stessa interfaccia di risultato.

## 14. Quality gates

Una regola o inferenza nuova deve avere:

- spiegazione;
- test;
- comportamento Unknown;
- definizione di input minimo;
- comportamento su dati stale/unavailable.
