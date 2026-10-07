# 12 — Home Assistant Integration

## 1. Obiettivo

Smart Compost Manager deve essere una vera integrazione Home Assistant, non uno script che vive accanto a Home Assistant.

Deve seguire le convenzioni moderne dell'ecosistema e verificare la documentazione ufficiale corrente prima di ogni release.

## 2. Integration setup

La configurazione utente deve passare dal flusso UI appropriato di Home Assistant.

Il repository deve privilegiare Config Flow e una configurazione comprensibile.

## 3. Config entry

La configurazione deve essere separata concettualmente in:

- dati necessari all'identità/setup;
- opzioni modificabili.

Seguire la struttura attuale di Home Assistant per `ConfigEntry`.

## 4. Coordinator / update model

Il progetto può usare il pattern Coordinator o un altro pattern corrente appropriato.

Se viene usato un coordinator:

- centralizzare ciò che ha senso;
- evitare che ogni entity implementi una propria lettura duplicata;
- evitare polling inutile.

Il coordinator non deve diventare il contenitore di tutta la business logic.

## 5. Entities

Le entity devono essere derivate dallo stato del dominio.

## 6. Device registry

Ogni compost bin può essere rappresentato come device, con entity collegate.

L'implementazione deve rispettare le regole Home Assistant vigenti sul device registry e sulle config entries.

## 7. Unique IDs

Gli ID devono essere:

- stabili;
- non modificabili dall'utente;
- indipendenti dal nome visualizzato;
- non basati su IP temporanei.

## 8. Translations

Tutto ciò che l'utente vede deve essere localizzabile.

Questo include:

- config flow;
- options;
- entity names;
- errors;
- repairs/issues;
- device names quando applicabile;
- action/service descriptions;
- help text.

## 9. Availability

Distinguere:

- integrazione non disponibile;
- sensor source unavailable;
- valore Unknown;
- valore stale.

Una capability opzionale mancante non deve rendere inutilizzabile il bin.

## 10. Services / actions

Le azioni custom devono essere poche e motivate.

Esempi di capacità:

- start cycle;
- add material;
- record observation;
- record intervention;
- complete cycle.

Se una funzione esiste già nativamente in Home Assistant, non reinventarla.

## 11. Diagnostics

Prevedere diagnostics utili per:

- configuration;
- sensor mappings;
- capabilities;
- engine state summary;
- error states.

Mai includere segreti.

## 12. Repairs

Usare Repairs per problemi che richiedono un intervento configurativo dell'utente quando il pattern corrente di HA lo rende appropriato.

## 13. Testing

Il comportamento Home Assistant deve essere testato separatamente dal core.

## 14. Riferimenti ufficiali da verificare prima dell'implementazione/release

- Config Flow: https://developers.home-assistant.io/docs/core/integration/config_flow/
- Integration structure: https://developers.home-assistant.io/docs/creating_integration_file_structure/
- Entity: https://developers.home-assistant.io/docs/core/entity/
- Quality scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/

Le pagine ufficiali possono evolvere: la versione corrente della documentazione ha precedenza sui dettagli tecnici presenti in questo file.
