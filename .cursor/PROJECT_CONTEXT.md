# Cursor Project Context

## What this project is

Smart Compost Manager is a Home Assistant integration for intelligent compost management.

The intended experience is:

> "Tell me how my compost is doing, tell me why, and tell me whether I need to do anything."

## What this project is not

It is not:

- a generic sensor dashboard;
- a single temperature threshold alarm;
- a machine-learning experiment;
- a replacement for Home Assistant automations;
- a laboratory instrument;
- a system that should manufacture missing measurements.

## Core experience

The app follows this loop:

```text
Observe
→ Understand
→ Explain
→ Recommend
→ Verify
→ Learn
```

It must be able to answer "nothing to do" explicitly.

## Capability philosophy

Capabilities depend on available evidence.

Examples:

### No sensors

Possible:

- material tracking;
- manual observations;
- intervention tracking;
- weather context;
- estimated activity;
- limited phase estimation;
- diagnostics based on observations;
- general health with lower confidence;
- guide.

Unknown:

- measured internal temperature;
- measured internal moisture;
- exact oxygen level;
- actual pH without measurement.

### Temperature sensor

Additional capability:

- thermal trend;
- temperature events;
- stronger phase inference;
- thermophilic evidence;
- cooling detection;
- delta vs ambient.

### Temperature + humidity

Additional capability:

- moisture diagnostics;
- better aeration reasoning;
- richer health evaluation.

### Gas/VOC/NH3

Additional diagnostic evidence:

- possible odor/aeration/balance issues.

These signals do not prove a biological diagnosis by themselves.

## User mental model

The user should not need to understand C/N ratios, sensor theory or statistical confidence to use the integration.

Advanced details remain available in diagnostics/details.

## Implementation direction

Use current Home Assistant best practices, but let the current Home Assistant developer documentation determine the final technical choices.

The product documents define behavior. The implementation agent decides how to achieve it.
