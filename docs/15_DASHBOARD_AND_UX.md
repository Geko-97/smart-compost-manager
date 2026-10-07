# 15 — Dashboard and UX

## 1. Filosofia

La schermata principale è una **decision surface**, non un laboratorio.

## 2. Main view

Esempio:

```text
Garden Compost

Health 89/100
Healthy
Phase: Thermophilic
Confidence 94%

WHAT SHOULD I DO?
Nothing. The compost is behaving normally.

WHY?
Temperature is rising steadily and the current pattern matches active composting.
```

## 3. Problem view

```text
Garden Compost

Attention

Possible excessive moisture

WHAT SHOULD I DO?
Add dry structural brown material and improve aeration.

WHY?
Internal humidity is high, temperature is falling and recent rain may have increased moisture.

CONFIDENCE
87%
```

## 4. Priority principle

Mostrare una sola raccomandazione primaria.

Altri segnali possono esistere in Details.

## 5. Details page

Deve poter mostrare:

- current measurements;
- provenance;
- trends;
- Health breakdown;
- Phase;
- Activity;
- Diagnostics;
- Materials;
- Events;
- Interventions;
- Weather;
- Maturity;
- Learning/history.

## 6. "Why?"

Ogni stato significativo deve avere un approfondimento.

Esempio:

```text
Why is phase Thermophilic?
```

→ temperature evidence + duration + confidence.

## 7. "Unknown"

Deve essere leggibile:

> Internal moisture: Unknown — no compatible sensor is configured.

Non:

> Internal moisture: 0%.

## 8. Empty state

Senza sensori:

> No physical sensors are configured. The coach is using materials, observations, interventions and environmental context. Adding internal temperature will improve phase detection.

## 9. No action

Stato esplicito:

> All good — no action needed.

Non usare un UI neutra che lasci l'utente chiedersi se manca qualcosa.

## 10. Color accessibility

Il significato non deve dipendere solo dal colore.

Usare:

- text;
- icons;
- labels;
- severity words.

## 11. Advanced user

Gli utenti avanzati devono poter vedere:

- raw source;
- confidence;
- data quality;
- evidence;
- algorithmic explanation.

Ma non devono essere obbligati a farlo.

## 12. Dashboard performance

Evitare grafici/attributes che generano inutilmente molti state changes.

## 13. Consistency

Lo stesso concetto deve avere lo stesso nome ovunque:

- Health;
- Confidence;
- Data Quality;
- Phase;
- Activity;
- Maturity.
