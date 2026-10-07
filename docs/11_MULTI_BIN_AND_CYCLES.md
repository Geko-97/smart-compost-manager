# 11 — Multi Bin and Cycles

## 1. Multi-bin first-class

Uno degli obiettivi architetturali fondamentali è supportare più compost bin in modo nativo.

## 2. Isolation invariant

Questo deve essere sempre vero:

```text
Bin A ≠ Bin B
```

A meno che l'utente non crei esplicitamente un'aggregazione.

## 3. Isolamento richiesto

Separare:

- config;
- sensor bindings;
- materials;
- observations;
- interventions;
- current state;
- history;
- learning;
- forecasts;
- notifications.

## 4. Bin identity

Usare ID stabile interno.

Il display name è modificabile.

## 5. Continuous composting

Il bin può ricevere nuovo materiale mentre quello vecchio continua a maturare.

La UI deve evitare generalizzazioni del tipo:

> all material in bin is mature.

## 6. Batch composting

Un batch rappresenta un ciclo logico isolabile.

Il batch deve poter essere:

- avviato;
- alimentato;
- monitorato;
- completato;
- maturato;
- archiviato.

## 7. Batch comparison

Confrontare:

- durata;
- picco termico;
- durata termofila;
- interventi;
- quantità materiali;
- output;
- tempi di maturazione;
- condizioni ambientali.

## 8. Learning per bin

Il sistema deve costruire baseline separate.

Un piccolo tumbler esposto al sole non dovrebbe ereditare automaticamente la baseline di un grande cumulo ombreggiato.

## 9. Current cycle

Un bin può avere:

```text
active cycle
```

oppure:

```text
no active cycle
```

## 10. Output

Un ciclo può registrare:

- quantità prodotta;
- unità;
- note;
- destinazione.

## 11. Deletion behavior

La cancellazione di un bin deve avere una politica chiara per:

- entity;
- device;
- history;
- cycle;
- persisted domain data.

Deve essere esplicita e non accidentale.

## 12. Future aggregation

In futuro può essere possibile un riepilogo globale:

```text
all compost
```

Ma l'aggregazione non deve cancellare la distinzione tra bin.
