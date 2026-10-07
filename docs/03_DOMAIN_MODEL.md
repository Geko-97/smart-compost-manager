# 03 — Domain Model

## 1. Principio

Il domain model deve descrivere il compost senza dipendere direttamente da Home Assistant.

Home Assistant fornisce input e interfaccia; il dominio rappresenta il significato.

## 2. CompostBin

Rappresenta il contenitore fisico.

Concettualmente:

```text
id
name
compost_type
mode
capacity
dimensions
environment_profile
sensor_bindings
active_cycle
created_at
updated_at
```

### Invarianti

- ID stabile;
- bin isolato;
- nome modificabile senza rompere lo storico;
- nessun sensor binding globale condiviso per errore.

## 3. CompostCycle

Rappresenta un periodo/ciclo logico.

```text
id
bin_id
mode
started_at
ended_at
status
materials
observations
interventions
phase_history
maturity_result
output
```

## 4. MaterialAddition

```text
timestamp
material_type
quantity
unit
quantity_precision
green_brown
estimated_properties
notes
```

## 5. Measurement

```text
parameter
value
unit
timestamp
source
availability
freshness
quality
provenance=MEASURED
```

Una measurement numerica non è automaticamente una buona measurement.

## 6. UserObservation

Esempio:

```text
category = odor
value = ammonia_like
timestamp
severity
notes
source = user
```

## 7. Intervention

Rappresenta qualcosa fatto al compost.

```text
timestamp
type
duration
source
reason
notes
```

## 8. Diagnostic

```text
code
severity
title
description
evidence
confidence
recommended_action
limitations
```

## 9. Recommendation

```text
priority
action
reason
evidence
confidence
estimated_effect
verification_window
automation_possible
```

## 10. Derived State

Possibili risultati:

- phase;
- activity;
- moisture status;
- aeration status;
- balance status;
- health;
- maturity;
- pest risk.

Ogni risultato deve avere provenance.

## 11. Evidence

Una evidence deve essere concreta:

```text
source
parameter
value
timestamp
interpretation_role
```

Esempio:

```text
parameter = temperature_slope
value = -1.8 C/hour
role = supports_cooling
```

## 12. Unknown

Unknown non è errore.

Esempi:

```text
pH = Unknown
internal_moisture = Unknown
oxygen = Unknown
```

## 13. Result objects

È preferibile restituire risultati strutturati rispetto a numeri nudi.

Esempio concettuale:

```text
HealthResult
    score
    confidence
    components
    evidence
    limitations
```

## 14. Enum centralizzati

Stati, tipi di evento, provenance, severity e modalità devono avere una rappresentazione centralizzata e stabile.

## 15. Quantità qualitative

L'utente può non pesare il materiale.

Quindi:

```text
small
medium
large
handful
approximate
```

sono dati validi, purché non vengano successivamente rappresentati come misure precise.

## 16. Domain boundaries

Non inserire nel dominio:

- UI text;
- Home Assistant entity objects;
- service call objects;
- frontend logic.
