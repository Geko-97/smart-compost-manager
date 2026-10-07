# Cursor Instructions — Smart Compost Manager

## 1. Role

You are the implementation agent for Smart Compost Manager.

The human defines the product goal, desired user experience, domain concepts, safety principles and acceptance criteria.

You determine the appropriate implementation details using current Home Assistant patterns and sound software engineering.

Do not mistake this document for a request to implement every item immediately. Work incrementally according to `docs/25_ROADMAP.md`.

## 2. Mandatory reading order

Before a substantial change, inspect:

1. `README.md`;
2. `docs/00_PROJECT_OVERVIEW.md`;
3. the document(s) directly related to the change;
4. relevant tests;
5. existing integration code.

For Home Assistant API details, verify the current official developer documentation rather than relying only on this repository.

## 3. Product invariants

### 3.1 Never invent data

Never turn:

- missing sensor → fabricated value;
- unavailable sensor → cached measurement presented as current;
- ambient humidity → internal compost moisture;
- theoretical material C/N → measured C/N;
- model inference → physical measurement.

### 3.2 Preserve provenance

Every meaningful value or conclusion must retain enough metadata to distinguish:

- measured;
- user-provided;
- estimated;
- inferred;
- unknown.

### 3.3 Preserve Unknown

Unknown is a valid state.

Do not "fix" Unknown simply to make the UI look complete.

### 3.4 Separate concepts

Never collapse:

- Health;
- Confidence;
- Data Quality.

### 3.5 Multi-bin isolation

No event, measurement, intervention, forecast, learning statistic or diagnosis from one bin may silently affect another bin.

### 3.6 No duplicate physical sensors

User sensors remain external inputs.

Create derived entities, not shadow copies.

### 3.7 Explainability

Important recommendations must expose evidence and limitations.

### 3.8 Safe automation

An automatic physical action must be explicit, opt-in, constrained and safe on Unknown/stale input.

### 3.9 Core independence

The compost reasoning engine must not require Home Assistant objects in its domain logic.

## 4. Implementation freedom

You may choose:

- exact Python module boundaries;
- dataclasses / typed models / enums;
- coordinator implementation;
- repository abstraction;
- event listeners;
- timers;
- storage mechanism;
- test fixtures;
- selectors;
- entity platform structure;

provided that the resulting implementation satisfies the product documents.

Do not preserve an implementation idea from this documentation if current Home Assistant guidance clearly recommends a better current pattern. Preserve the **behavioral requirement**, not an outdated API pattern.

## 5. Anti-patterns

Do not introduce:

```python
value = state or 0
```

when zero is not semantically correct.

Do not introduce broad:

```python
except Exception:
    pass
```

Do not hardcode user-facing English strings in Python if they should be translated.

Do not use unstable values for unique IDs.

Do not create huge mutable global state.

Do not put all business logic into the coordinator or entity classes.

Do not build an entire dashboard as a collection of raw sensors.

## 6. Scientific language

When evidence is limited, use:

- possible;
- likely;
- may indicate;
- insufficient data;
- estimated;
- inferred.

Avoid absolute diagnoses unless the evidence genuinely supports them.

## 7. Change discipline

For each feature:

1. understand the domain requirement;
2. choose an implementation;
3. add tests;
4. implement;
5. run tests/lint/format available locally;
6. test Unknown/unavailable behavior;
7. inspect multi-bin boundaries;
8. check translations;
9. update docs if behavior changed.

Prefer small, coherent changes.

## 8. Definition of success

The implementation is successful when the user can trust the system.

A smaller feature that is truthful and explainable is better than a larger feature that gives false precision.
