# 19 — Data Storage

## 1. Obiettivo

Conservare ciò che serve al dominio senza duplicare inutilmente ciò che Home Assistant già conserva.

## 2. Configuration data

Gestire:

- bins;
- sensor bindings;
- environment;
- notification preferences;
- automation preferences;
- retention settings.

## 3. Domain data

Gestire:

- cycles;
- material additions;
- observations;
- interventions;
- important event metadata;
- cycle summaries;
- learning aggregates se necessari.

## 4. Sensor history

Non replicare automaticamente tutto lo storico di Home Assistant.

Quando HA fornisce già uno storico, Smart Compost Manager deve sfruttarlo o dipendere da una strategia efficiente, invece di creare un secondo database completo.

## 5. Raw vs aggregate

Il progetto può usare:

```text
raw relevant events
hourly/daily aggregates
cycle summaries
```

La strategia precisa è una scelta implementativa.

## 6. High-frequency data

Non scrivere ogni variazione ad alta frequenza come dato applicativo permanente se non serve.

## 7. Schema versioning

Ogni struttura persistente propria deve avere una strategia di versioning e migration.

## 8. Restart

Dopo restart devono essere ricostruibili:

- bin;
- binding;
- cycle;
- important state.

## 9. Corruption

Un dato corrotto non deve abbattere l'intera integrazione.

Strategia desiderata:

- log;
- recovery;
- fallback;
- repair message quando appropriato.

## 10. Retention

La retention deve essere conservativa.

L'utente deve sapere che cosa viene cancellato e cosa resta nello storico HA.

## 11. Data reset

Prevedere una procedura chiara per:

- reset current cycle;
- archive cycle;
- clear domain history;
- remove bin.

## 12. Privacy

Persistono solo dati utili al funzionamento del prodotto.

## 13. Source of truth

Home Assistant resta il source of truth per gli stati delle entity esterne.

Smart Compost Manager è proprietario dei dati applicativi che l'utente inserisce direttamente nell'integrazione e delle strutture di dominio che HA non conosce.
