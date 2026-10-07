# 22 — Local Development

## 1. Obiettivo

Il progetto parte in un ambiente locale con Home Assistant in Docker.

## 2. Development layout

```text
smart-compost-manager/
```

deve essere il repository principale.

La cartella di integrazione sarà:

```text
custom_components/smart_compost/
```

Il progetto può essere montato nel container HA verso:

```text
/config/custom_components/smart_compost/
```

secondo il setup locale.

## 3. Development cycle

```text
change
→ tests
→ lint/format
→ install/reload
→ manual check
→ logs
→ regression
→ commit
```

## 4. First milestone

Non iniziare dalla versione completa.

Iniziare con:

- manifest;
- config flow;
- one compost bin;
- domain model;
- zero-sensor capability;
- basic entities;
- tests.

## 5. Test fixtures

Preparare scenari sintetici:

### Scenario A
No sensors + simple material log.

### Scenario B
Temperature rise.

### Scenario C
Thermal peak and cooling.

### Scenario D
High moisture + cooling.

### Scenario E
Drying + hot weather.

### Scenario F
Turning + response.

### Scenario G
Two bins.

### Scenario H
Sensor removed.

## 6. Docker development

La versione Home Assistant usata per i test deve essere annotata nella documentazione di sviluppo e aggiornata periodicamente.

Cursor deve verificare compatibilità con la versione reale usata.

## 7. Debug

Usare log level appropriati.

La modalità debug deve essere utile senza trasformare il log in migliaia di righe inutili.

## 8. Git

Commit piccoli:

```text
feat: add compost cycle model
feat: add health engine
fix: preserve unknown moisture state
test: add bin isolation regression
docs: clarify continuous maturity
```

## 9. Local test philosophy

Non considerare una feature conclusa perché "funziona sul mio bin".

Deve funzionare con:

- dato mancante;
- sensore indisponibile;
- dati fuori range;
- più bin;
- restart;
- configuration changes.

## 10. Cursor collaboration

L'utente non deve decidere:

> quale classe usare.

Deve poter decidere:

> cosa deve comportarsi in questo modo.

Cursor deve proporre e applicare l'implementazione migliore, spiegando eventuali scelte che cambiano il comportamento del prodotto.
