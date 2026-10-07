# 14 — Config Flow and Settings

## 1. Obiettivo

La configurazione deve guidare un principiante senza nascondere le opzioni avanzate.

## 2. Setup flow desiderato

```text
Welcome
→ Language
→ Create compost bin
→ Compost type
→ Composting method
→ Environment
→ Sensor association
→ Notifications
→ Finish
```

Il flusso esatto può essere adattato a Home Assistant corrente.

## 3. Zero-sensor path

Deve esistere esplicitamente:

> I don't have sensors / Skip sensors.

Il percorso senza sensori non deve sembrare un errore.

## 4. Compost type

La selezione deve usare concetti semplici:

- enclosed bin;
- tumbler;
- open pile;
- garden compost;
- other.

Se un tipo futuro richiede un modello diverso, deve essere gestito come capability.

## 5. Composting method

```text
Continuous
Batch
```

La differenza deve essere spiegata in linguaggio non tecnico.

## 6. Environment

Permettere:

- indoor/outdoor;
- shelter;
- rain exposure;
- sun exposure.

## 7. Sensors

Le categorie devono essere:

- temperature;
- internal humidity;
- VOC;
- ammonia;
- CO2;
- weight;
- fill;
- ambient temperature/humidity;
- weather.

La discovery deve aiutare ma non assegnare in modo rischioso entity ambigue.

## 8. Options Flow

Deve permettere di modificare nel tempo:

- nome;
- tipo;
- mode;
- environment;
- sensors;
- notifications;
- automation;
- retention;
- advanced preferences.

## 9. Sensor removal

La rimozione non deve richiedere reinstallazione.

## 10. Notifications

L'utente deve poter attivare/disattivare categorie built-in.

## 11. Automation settings

Se esistono attuatori:

- deve esistere un consenso esplicito;
- limiti;
- duration;
- cooldown;
- comportamento su Unknown;
- fallback safe.

## 12. Data settings

Possibili:

- retention;
- clear history;
- start new cycle;
- archive cycle.

## 13. Localization

Config flow e options devono usare le strutture di traduzione attuali.

## 14. Validation

Validare:

- input invalidi;
- entity references;
- compatibilità di settings;
- duplicazione accidentale;
- configurazioni impossibili.

## 15. Reconfiguration

Il progetto deve essere pensato per permettere di correggere la configurazione senza ricreare tutto, in linea con le pratiche HA correnti.
