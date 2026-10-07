# 16 — Notifications and Actions

## 1. Obiettivo

Notificare solo quando la notifica aiuta davvero.

## 2. Severity levels

```text
INFO
SUGGESTION
RECOMMENDED
URGENT
```

## 3. Candidate notifications

- phase changed;
- thermophilic detected;
- health degraded;
- health recovered;
- moisture issue;
- possible aeration issue;
- possible material imbalance;
- strong anomaly;
- likely mature;
- batch ready;
- intervention recommended;
- intervention appears effective;
- sensor unavailable;
- sensor restored;
- data quality degraded;
- new cycle;
- cycle completed;
- extreme weather risk.

## 4. Notification fatigue

Ogni categoria deve supportare concetti di:

- persistence;
- cooldown;
- deduplication;
- recovery;
- priority.

## 5. Notification content

Idealmente:

```text
What
Why
Action
Confidence
```

## 6. Example

> Compost moisture may be too high.
>
> Internal humidity has remained elevated while temperature is falling. Recent watering was also recorded.
>
> Consider adding dry structural material and checking compaction.
>
> Confidence: 82%.

## 7. No notification for noise

Un sensore che oscilla leggermente non deve generare una sequenza infinita di:

- issue;
- recovered;
- issue;
- recovered.

## 8. Built-in vs custom automation

Built-in notification:

> integration decides when to notify.

Custom HA automation:

> user decides a condition and action.

Il sistema deve supportare entrambe le cose.

## 9. Action recommendation

Una recommendation non attiva nulla automaticamente.

Esempio:

```text
Recommendation: add water
```

non significa:

```text
turn irrigation on
```

## 10. Physical automation

Se implementata:

- opt-in;
- explicit enable;
- max duration;
- cooldown;
- safe on stale/unknown;
- manual override;
- clear state.

## 11. Service/action design

Actions devono essere idempotenti dove possibile o documentare chiaramente gli effetti ripetuti.

## 12. Verification

Dopo una action, il sistema può verificare la risposta del compost.

Se non c'è evidenza sufficiente:

> Result unknown.

Non inventare "success".
