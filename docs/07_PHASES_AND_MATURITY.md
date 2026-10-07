# 07 — Phases and Maturity

## 1. Obiettivo

Phase e Maturity sono concetti diversi.

- Phase = cosa sta probabilmente accadendo nel processo.
- Maturity = quanto il materiale è probabilmente pronto per uno specifico uso.

## 2. Phase model

```text
NEW_CYCLE
ACTIVATION
MESOPHILIC
THERMOPHILIC
COOLING
MATURATION
MATURE
UNKNOWN
```

## 3. Phase confidence

Ogni phase result deve avere:

- phase;
- provenance;
- confidence;
- evidence;
- limitations.

## 4. Con sensore di temperatura

La serie termica deve essere analizzata, non solo il valore attuale.

Considerare:

- partenza;
- aumento;
- velocità;
- picco;
- durata;
- discesa;
- nuovi picchi;
- temperatura ambientale.

## 5. Senza sensore

Il sistema può usare:

- materiali;
- tempo;
- interventi;
- osservazioni;
- storico.

Ma non deve dichiarare una fase termica specifica come osservata.

Esempio corretto:

> Activity appears elevated; internal thermal phase cannot be confirmed because no temperature sensor is configured.

## 6. Thermophilic

L'evidenza termofila deve dipendere dalla temperatura interna e dalla durata, non dal semplice calendario.

Le soglie esatte sono un dettaglio implementativo da definire e testare.

## 7. Cooling

La fase di cooling richiede una discesa persistente dopo attività precedente, non un singolo calo.

## 8. Maturation

Possibili segnali:

- temperatura vicina all'ambiente;
- stabilità;
- nessun nuovo picco rilevante;
- tempo sufficiente;
- degradazione osservabile;
- storia del batch;
- eventuali indicatori di qualità.

## 9. Maturity is contextual

"Pronto" deve indicare per cosa.

Possibili output:

```text
ready_for_curing
likely_mature
likely_suitable_for_garden_use
unknown
```

## 10. Continuous mode

In un bin continuo esistono materiali a età diverse.

Il motore deve evitare di generalizzare lo stato dell'intero contenitore quando il materiale è eterogeneo.

## 11. Batch mode

Il batch è il candidato naturale per una maturity decision più netta.

## 12. Maturity forecast

Il forecast deve produrre una finestra, non una data falsamente precisa:

```text
Estimated maturity window:
10–18 days
Confidence:
61%
```

Non:

```text
Ready at 16:32 on 24 July
```

a meno che un modello e i dati lo giustifichino davvero.

## 13. Agronomic caution

La maturity estimate non è:

- certificazione sanitaria;
- analisi di laboratorio;
- garanzia di fitotossicità zero;
- garanzia agronomica.

La guida deve chiarire i limiti.
