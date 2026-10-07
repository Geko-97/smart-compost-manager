# 04 — Data Provenance

## 1. Scopo

La provenance è un requisito fondamentale di affidabilità.

Il sistema deve sapere non solo "quanto vale una variabile", ma anche:

> da dove arriva e quanto è affidabile.

## 2. Cinque categorie

### Measured

Direttamente da un sensore/entity.

### User-provided

Inserita dall'utente.

### Estimated

Prodotta da una regola/stima quantitativa.

### Inferred

Conclusione ricavata dall'insieme delle evidenze.

### Unknown

Non determinabile.

## 3. Esempi

```text
Internal temperature = 57.8 °C
provenance = measured
```

```text
Amount of leaves = 2 buckets
provenance = user_provided
quantity_precision = approximate
```

```text
Activity = high
provenance = inferred
```

```text
pH = unknown
```

## 4. Provenance e availability sono diverse

Un sensore può essere:

```text
provenance = measured
availability = unavailable
```

In quel momento non è valido dire che l'attuale valore sia misurato.

## 5. Provenance e confidence sono diverse

Una misura reale può avere bassa confidence come evidenza di una diagnosi.

Esempio:

- temperatura misurata;
- ma senza moisture;
- e il problema riguarda l'umidità.

La measurement resta measured, ma la diagnosi può avere confidence bassa.

## 6. Provenance e data quality

Data Quality descrive l'insieme dei dati disponibili.

Può dipendere da:

- completezza;
- continuità;
- freschezza;
- affidabilità;
- copertura temporale.

## 7. Ambient vs internal

Questa distinzione deve essere assoluta.

```text
ambient_temperature
```

non è:

```text
compost_temperature
```

```text
ambient_humidity
```

non è:

```text
compost_moisture
```

Il weather può fornire contesto ma non sostituisce la measurement interna.

## 8. Estimated C/N

Un C/N interno della knowledge base può essere usato per calcolare una stima.

Non deve apparire come:

> measured C/N.

## 9. UI

L'utente deve poter scoprire la provenance nella vista dettagliata.

La schermata principale può sintetizzare:

```text
Confidence 72%
```

senza mostrare badge su ogni valore.

## 10. Unknown behavior

Quando un input diventa Unknown:

1. propagare Unknown solo alle dipendenze;
2. mantenere operative le parti indipendenti;
3. ridurre confidence/data quality dove giustificato;
4. spiegare la limitazione quando è rilevante.

## 11. Auditability

Per diagnosi importanti deve essere possibile ricostruire:

- quali evidenze erano disponibili;
- quali regole/modelli sono stati usati;
- quale risultato è stato prodotto;
- con quale confidence.

## 12. Regola anti-hallucination

Prima di mostrare un valore chiedersi:

> È una misura, un input, una stima, una inferenza o non lo sappiamo?

Se la risposta non è chiara, il valore non è pronto per essere mostrato come fatto.
