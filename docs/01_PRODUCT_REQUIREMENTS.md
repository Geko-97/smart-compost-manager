# 01 — Product Requirements

## 1. Obiettivo

Questo documento definisce ciò che il prodotto deve fare. Non prescrive il codice.

Cursor deve scegliere l'implementazione migliore compatibile con Home Assistant e con gli altri documenti.

## 2. Requisiti core

### PR-001 — Installazione senza sensori

L'utente deve poter completare la configurazione con zero sensori.

### PR-002 — Utilità senza sensori

Senza sensori devono essere disponibili almeno:

- bin management;
- cycles/batches;
- materials;
- observations;
- interventions;
- guide;
- limited diagnosis;
- estimated activity/phase dove logicamente sostenibile;
- Health con confidence ridotta;
- Data Quality.

### PR-003 — Progressive capability

L'aggiunta di un sensore deve abilitare capacità ulteriori senza ricreare l'intero sistema.

### PR-004 — Rimozione sensore

La rimozione deve:

- disabilitare la capability dipendente;
- rendere il valore Unknown o non calcolabile;
- ridurre confidence/data quality quando pertinente;
- non rompere il bin.

### PR-005 — Physical sensor reuse

Associare una entity esistente, mai duplicarla.

### PR-006 — Multi-bin

Supportare almeno due bin contemporaneamente senza contaminazione dei dati.

### PR-007 — Continuous mode

Il sistema deve supportare contenuto che cambia continuamente.

### PR-008 — Batch mode

Il sistema deve supportare cicli/batch isolabili e confrontabili.

### PR-009 — Data provenance

Ogni risultato significativo deve conservare provenance.

### PR-010 — Explainability

Le conclusioni importanti devono avere evidence.

### PR-011 — Health

Health 0–100, aggregato solo dalle componenti valutabili, con gestione esplicita dell'incertezza.

### PR-012 — Confidence

Confidence 0–100, distinta da Health.

### PR-013 — Data Quality

Data Quality 0–100, distinta da Health e Confidence.

### PR-014 — Phase

Supportare il modello di fase documentato in `07_PHASES_AND_MATURITY.md`.

### PR-015 — Maturity

Non dichiarare maturità da una sola variabile.

### PR-016 — Diagnostics

Supportare diagnostica contestuale e probabilistica.

### PR-017 — Recommendations

Ogni raccomandazione deve avere priorità, motivo e confidence.

### PR-018 — No-action

"Nothing to do" deve essere uno stato valido e visibile.

### PR-019 — History

Supportare storico utile al motore, alle verifiche e all'apprendimento.

### PR-020 — Weather

Il weather deve essere contesto, non sostituto dei sensori interni.

### PR-021 — Material knowledge

L'app deve aiutare l'utente a bilanciare green/brown senza richiedere conoscenza tecnica del C/N.

### PR-022 — Human observations

Le osservazioni manuali devono essere first-class data, non note ignorate.

### PR-023 — Notifications

Devono essere configurabili e protette da persistence/cooldown/deduplication.

### PR-024 — Automation

Controlli fisici automatici solo con opt-in esplicito.

### PR-025 — Localization

Le stringhe utente devono essere traducibili.

### PR-026 — Diagnostics/Repairs

Dove utile, i problemi configurativi devono avere meccanismi nativi di diagnosi/riparazione.

### PR-027 — Recovery

Riavvio/reload dell'integrazione non deve causare perdita o duplicazione del dominio.

## 3. Qualità della risposta

Una risposta del sistema deve idealmente avere:

```text
STATE
ACTION
WHY
CONFIDENCE
LIMITATIONS
```

Non tutti i campi devono essere visualizzati sempre.

## 4. Requisiti anti-falsa-precisione

Non mostrare:

- 83.47% moisture se la moisture è una stima grossolana;
- C/N 29.42 come misura reale;
- ossigeno 16.2% senza sensore;
- "anaerobic" come fatto certo da un singolo VOC.

## 5. Requisiti di scalabilità

Il prodotto deve funzionare bene con:

- 1 bin;
- 2–5 bin;
- più bin in prospettiva.

La complessità computazionale e lo storage devono crescere in maniera ragionevole.

## 6. Requisiti UX

La prima schermata deve privilegiare decisioni e significato.

I dettagli possono essere disponibili a livelli successivi.

## 7. Requisiti per una release pubblicabile

Prima di GitHub/HACS:

- clean setup;
- no-sensor;
- single sensor;
- multi-sensor;
- multiple bins;
- restart/reload;
- migrations;
- translations;
- notification behavior;
- diagnostics;
- documentation;
- regression suite.
