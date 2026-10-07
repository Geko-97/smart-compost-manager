# 02 — Architecture

## 1. Architettura concettuale

```text
                 HOME ASSISTANT
                       │
             ┌─────────┴─────────┐
             │ Integration Layer │
             └─────────┬─────────┘
                       │
              Data Normalization
                       │
                 Domain Model
                       │
              ┌────────┴────────┐
              │  Compost Engine │
              └────────┬────────┘
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
     Health          Phase          Diagnostics
       │               │                │
       └───────────────┼────────────────┘
                       ▼
              Decision / Action Engine
                       │
              ┌────────┼─────────┐
              ▼        ▼         ▼
          Entities  Notifications Services
```

## 2. Responsabilità

### Integration Layer

Compito:

- leggere Home Assistant;
- ascoltare cambiamenti;
- validare input;
- convertire stati in dati di dominio;
- pubblicare risultati.

Non deve contenere tutta la logica del compost.

### Data Normalization

Compito:

- unità;
- timestamp;
- availability;
- freshness;
- source;
- provenance;
- quality.

### Domain Model

Compito:

- rappresentare compost, cicli, materiali, eventi e risultati.

Deve essere testabile senza Home Assistant.

### Compost Engine

Compito:

- estrarre feature;
- valutare condizioni;
- inferire stato;
- calcolare Health;
- classificare fase;
- valutare maturità;
- costruire diagnosi;
- produrre evidence;
- fornire forecast.

### Decision Engine

Compito:

- scegliere la diagnosi prioritaria;
- evitare overload;
- classificare la gravità;
- decidere se notificare;
- proporre una azione.

## 3. Principio "core first"

Il core dovrebbe essere utilizzabile con un oggetto di stato equivalente a:

```text
CompostState
    measurements
    observations
    materials
    interventions
    environment
    history
    cycle
```

e produrre:

```text
CompostAssessment
    health
    phase
    activity
    maturity
    diagnostics
    recommendation
    confidence
    data_quality
```

## 4. Event driven + time aware

Usare aggiornamenti event-driven dove ha senso.

Ma alcune decisioni richiedono il trascorrere del tempo:

- durata sopra soglia;
- stagnation;
- cooling;
- maturation;
- cooldown;
- verification window.

Quindi il sistema deve avere sia:

- reaction to events;
- periodic evaluation.

## 5. Stato e storico

Non confondere:

- stato attuale;
- evento storico;
- serie temporale;
- statistica aggregata.

## 6. Isolamento per bin

Tutti i flussi devono portare un identificatore stabile del bin.

Nessuna funzione centrale deve operare implicitamente su "the current bin" senza contesto.

## 7. Error isolation

Un input guasto deve degradare la sola capability coinvolta.

Esempio:

```text
temperature sensor unavailable
```

non implica:

```text
whole integration unavailable
```

## 8. Estensibilità

L'architettura deve permettere in futuro:

- più fonti;
- più strategie di scoring;
- modelli statistici;
- ML;
- garden integration.

Senza riscrivere il provenance model.

## 9. Prestazioni

Evitare:

- ricalcolo completo di tutto lo storico a ogni aggiornamento;
- scrittura persistente a ogni campione rumoroso;
- attributes enormi e variabili troppo frequenti;
- log ad alta frequenza.

## 10. Decisione finale dell'implementazione

La documentazione indica il comportamento, non la forma esatta delle classi.

Cursor deve scegliere la soluzione che aderisce meglio alle pratiche Home Assistant correnti e che resta facilmente testabile.
