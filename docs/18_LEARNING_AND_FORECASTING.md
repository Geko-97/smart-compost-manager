# 18 — Learning and Forecasting

## 1. Strategia

La prima versione deve preferire:

```text
Rules
→ Statistics
→ Personal baseline
→ Forecasting
→ optional future ML
```

Non partire dal machine learning.

## 2. Personal baseline

Il comportamento normale dipende dal singolo bin.

Esempio:

> This bin usually heats within 12–24 hours after a balanced addition.

È più utile se supportato da sufficiente storico.

## 3. Statistics

Raccogliere, quando disponibile:

- activation time;
- max temperature;
- duration above thermal thresholds;
- cooling duration;
- maturation duration;
- output;
- interventions;
- response to watering;
- response to turning;
- seasonal effects.

## 4. Minimum history

Non costruire una baseline affidabile dopo poche osservazioni.

La soglia minima deve essere definita, testata e documentata.

## 5. Forecast outputs

Possibili:

- maturity window;
- expected thermal trend;
- moisture risk;
- drying risk;
- rain impact;
- slowdown risk.

## 6. Confidence

Ogni forecast deve avere confidence.

Più il forecast è lontano o i dati sono incompleti, più deve degradare confidence.

## 7. Personalization

Il sistema deve preferire il comportamento del bin rispetto a soglie universali quando la baseline è sufficientemente affidabile.

## 8. Intervention learning

Dopo interventi, memorizzare:

```text
intervention
before
after
time window
observed response
confidence
```

## 9. Causality warning

Il prodotto non deve dichiarare causalità certa da osservazioni naturalistiche.

## 10. Future ML

Un futuro modello deve ricevere un dataset con provenance.

Non deve usare dati "unknown" come zero.

Deve produrre:

```text
prediction
confidence
evidence
limitations
```

## 11. Privacy

Learning deve essere locale per default, salvo futura scelta esplicita di servizi esterni.

## 12. Explainable forecast

Esempio:

> Estimated maturity window: 10–18 days.
>
> Why: similar cycles in this bin reached stable maturation in 12–19 days under comparable temperature conditions.
>
> Confidence: 68%.
