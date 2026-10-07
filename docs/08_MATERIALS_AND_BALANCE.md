# 08 — Materials and Balance

## 1. Obiettivo

L'utente deve poter registrare materiali senza dover capire il C/N scientifico.

L'app traduce le scelte in conseguenze pratiche.

## 2. Material knowledge model

Ogni categoria può avere:

```text
green_brown
estimated_cn
moisture_contribution
structural_contribution
decomposition_speed
density
acidity_tendency
usage_level
notes
```

Questi sono dati di conoscenza/stima.

## 3. Materiali iniziali

Categorie semplici:

- food scraps;
- fresh grass;
- coffee grounds;
- dry leaves;
- cardboard;
- straw;
- small woody material;
- garden waste;
- other.

L'elenco deve essere estendibile.

## 4. Usage level

```text
recommended
acceptable
use_sparingly
avoid
```

"Allowed" non basta a descrivere il contesto.

## 5. Quantità

Supportare:

- exact;
- approximate;
- qualitative.

Esempio:

```text
quantity = 2
unit = bucket
precision = approximate
```

## 6. Green/Brown

Sono categorie funzionali, non una descrizione completa del materiale.

Un materiale brown molto fine può contribuire poco alla struttura.

## 7. Structure

Ogni materiale può contribuire:

```text
low
medium
high
```

alla struttura.

Questo aiuta l'aeration engine.

## 8. Balance

Il sistema può stimare pressioni:

- green/wet pressure;
- brown/dry pressure;
- structural pressure;
- moisture pressure.

Non deve pretendere di conoscere l'esatta composizione chimica del bin.

## 9. Context

La raccomandazione deve essere contestuale.

Esempio:

```text
food scraps added
+
bin already wet
```

→

> Consider adding dry structural brown material.

Non applicare una ricetta fissa universale.

## 10. Quantitative recommendations

Una quantità numerica precisa deve essere prodotta solo quando:

- gli input sono sufficientemente affidabili;
- la formula è documentata;
- la precisione è comunicata come stima.

Altrimenti preferire indicazioni qualitative.

## 11. Material history

Il sistema deve poter ricostruire:

- cosa;
- quanto;
- quando;
- in quale ciclo;
- cosa è successo dopo.

## 12. User experience

La UI deve partire da linguaggio comune.

Esempio:

> Add dry brown material

 e non:

> Increase the C/N ratio by 15%.

Il dettaglio tecnico può apparire nella spiegazione avanzata.
