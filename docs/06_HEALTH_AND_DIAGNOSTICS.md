# 06 — Health and Diagnostics

## 1. Health

Health risponde:

> Quanto sembra sano il processo di compostaggio sulla base delle evidenze disponibili?

Range:

```text
0–100
```

Non è una misura fisica.

## 2. Componenti

Le dimensioni concettuali sono:

- Thermal Health;
- Moisture Health;
- Aeration Health;
- Balance Health;
- Biological Activity;
- Cycle Progress.

Cursor può cambiare la formula tecnica, ma deve conservare questa separazione semantica.

## 3. Aggregazione

Se una componente non è valutabile:

- segnalarla come unavailable/unknown;
- non darle un punteggio arbitrario;
- ricalibrare il peso delle componenti disponibili;
- ridurre confidence/data quality quando appropriato.

## 4. Esempio

```text
Health = 88
Confidence = 34
Data Quality = 27
```

Interpretazione:

> Le poche evidenze disponibili sono positive, ma il sistema sa poco.

## 5. Diagnostic catalogue

### Moisture

- likely too dry;
- possible too dry;
- likely too wet;
- possible too wet;
- insufficient moisture data.

### Aeration

- possible compaction;
- possible poor aeration;
- aeration appears adequate;
- insufficient data.

### Balance

- possible excess wet green;
- possible excess dry carbon;
- balance appears reasonable;
- insufficient data.

### Thermal

- weak heating;
- rapid heating;
- active heating;
- thermophilic evidence;
- rapid cooling;
- stagnation.

### Environment

- drying risk;
- rain risk;
- cold slowdown;
- heat exposure.

### Pest

- elevated pest risk;
- observed flies;
- observed rodents;
- other observed pest.

## 6. Severity

```text
INFO
SUGGESTION
RECOMMENDED
URGENT
```

## 7. Priority

La priorità considera concettualmente:

- severity;
- confidence;
- persistence;
- potential impact;
- actionability;
- recency.

## 8. Diagnosi probabilistiche

Preferire:

> Possible excessive moisture.

a:

> The compost is anaerobic.

La seconda affermazione richiederebbe una evidenza molto più forte.

## 9. Why view

Ogni diagnosi importante deve avere una spiegazione del tipo:

```text
Why?
- humidity has remained high;
- temperature has fallen;
- recent watering occurred;
- VOC increased.
```

## 10. Evidence hierarchy

Una evidence può essere:

- direct measurement;
- repeated observation;
- recent event;
- historical pattern;
- weather context;
- model estimate.

Le evidenze devono essere pesate in funzione dell'affidabilità.

## 11. False precision

Non mostrare decimali inutili nei punteggi.

```text
Health: 83
```

è preferibile a:

```text
Health: 83.426718
```

## 12. Recovery

Quando una condizione negativa cessa in modo persistente, il sistema può produrre:

> Compost health recovered.

La recovery notification deve rispettare cooldown e persistence.

## 13. Stale data

Un sensore con dati troppo vecchi può non essere trattato come current.

La freshness policy deve essere definita per tipo di dato e verificata nel codice.
