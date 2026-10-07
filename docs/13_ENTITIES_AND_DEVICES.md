# 13 — Entities and Devices

## 1. Principle

L'integrazione rappresenta un compost bin come dispositivo logico e pubblica soprattutto risultati derivati.

## 2. Candidate entities

Per ogni bin, considerare:

- Compost Health;
- Compost Phase;
- Compost Activity;
- Compost Confidence;
- Compost Data Quality;
- Compost Estimated Maturity;
- Compost Current Cycle;
- Compost Moisture Status;
- Compost Aeration Status;
- Compost Pest Risk;
- Compost Priority Action.

Non è obbligatorio creare tutte le entity: una entity deve esistere perché utile, non per riempire la dashboard.

## 3. Input sensors

Gli input possono essere entity di altri domini/integrations.

Esempi:

- temperature;
- humidity;
- VOC;
- NH3;
- CO2;
- weight;
- fill level;
- weather.

L'associazione deve essere esplicita quando l'auto-discovery non è sufficientemente sicura.

## 4. No duplicate physical sensors

Mai creare un clone di:

```text
sensor.compost_temperature
```

solo per esporlo tramite Smart Compost Manager.

## 5. Derived states

Un valore come:

```text
sensor.compost_health = 84
```

è un indice derivato.

Non deve avere una provenance implicita di "measured".

## 6. Unknown

Possibili pattern:

```text
phase = unknown
```

oppure una entity diagnostic/derived può restare disponibile con stato Unknown secondo ciò che supporta il dominio.

La decisione concreta deve seguire le convenzioni HA correnti.

## 7. Entity names

Usare naming tradotto e device association coerente.

Evitare di incorporare il nome del device nella entity name quando Home Assistant può comporlo automaticamente.

## 8. Attributes

Attributes devono essere piccoli e utili.

Per esempio Health può esporre:

```text
score
confidence
data_quality
top_issue
```

Non inserire l'intero storico nel state attributes.

## 9. Entity categories

Le entity devono essere classificate appropriatamente.

Le entity meno utili o diagnostiche possono essere disabled-by-default quando appropriato.

## 10. State translations

Fasi e stati devono poter essere tradotti.

## 11. Icons

Valutare icon translations quando appropriate secondo le convenzioni Home Assistant correnti.

## 12. Device identity

Il device deve avere identificatore stabile associato al bin.

Il nome visualizzato può cambiare.

## 13. Main vs diagnostic

Separare le entity essenziali da quelle avanzate.

La UI principale non deve dipendere dall'esposizione di ogni dettaglio come entity.
