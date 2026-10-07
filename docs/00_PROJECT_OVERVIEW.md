# 00 — Project Overview

## 1. Vision

Smart Compost Manager deve diventare il "Compost Coach" di Home Assistant.

Non si limita a dire:

> temperatura = 57 °C.

Deve trasformare i dati disponibili in un modello comprensibile:

> Il compost è in fase attiva, la temperatura interna sta salendo e il comportamento è coerente con il ciclo attuale. Non serve intervenire.

Quando emerge un problema:

> Possibile eccesso di umidità. La temperatura è in calo, l'umidità interna è elevata e ci sono state piogge recenti. Valuta l'aggiunta di materiale marrone asciutto e strutturale.

La seconda risposta deve essere accompagnata da evidenze, limiti e confidence.

## 2. Missione

Il prodotto deve massimizzare:

- utilità;
- precisione interpretativa;
- trasparenza;
- continuità storica;
- facilità d'uso;
- adattabilità all'hardware;
- sicurezza.

Deve minimizzare:

- falsi allarmi;
- rumore;
- duplicazione di dati;
- configurazioni inutilmente tecniche;
- falsa precisione;
- dipendenze obbligatorie.

## 3. Product loop

```text
OBSERVE
  ↓
NORMALIZE
  ↓
UNDERSTAND
  ↓
EXPLAIN
  ↓
RECOMMEND
  ↓
VERIFY
  ↓
LEARN
  ↺
```

## 4. Le quattro domande

Ogni principale stato del sistema deve essere riconducibile a:

1. **Come sta?**
2. **Perché lo dici?**
3. **Devo fare qualcosa?**
4. **Quanto sei sicuro?**

## 5. Dimensione del progetto

Il modello deve poter evolvere:

```text
zero sensors
→ temperature
→ temperature + moisture
→ environment
→ materials
→ gas signals
→ weight/fill
→ maturity
→ learning
→ future advanced models
```

## 6. Copertura del dominio

### Physical

- temperature;
- moisture;
- mass;
- volume;
- fill level;
- structure;
- compaction;
- dimensions.

### Environmental

- ambient temperature;
- ambient humidity;
- precipitation;
- wind;
- solar exposure;
- shelter;
- season.

### Material

- type;
- quantity;
- Green/Brown;
- estimated C/N;
- moisture contribution;
- structural contribution;
- decomposition speed;
- density;
- caution level.

### Chemistry / gas

- VOC;
- NH3;
- CO2;
- pH;
- EC/salinity.

Queste variabili hanno priorità diverse. Non tutte devono essere obbligatorie.

### Human observations

- dry;
- wet;
- smell;
- flies;
- larvae;
- worms;
- pests;
- compaction;
- appearance.

### Events

- additions;
- watering;
- turning;
- aeration;
- corrections;
- phase changes;
- anomalies.

### Derived

- Health;
- Activity;
- Phase;
- Balance;
- Moisture status;
- Aeration status;
- Maturity;
- Forecast;
- Confidence;
- Data Quality;
- Pest Risk;
- Priority Action.

## 7. Guiding rule

La completezza del prodotto non significa "raccogliere tutto".

Significa:

> essere in grado di rappresentare una variabile quando è disponibile, riconoscerne l'assenza quando non è disponibile e usare solo ciò che è appropriato per prendere una decisione.
