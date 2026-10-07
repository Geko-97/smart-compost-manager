# 26 — Definition of Done

## 1. Product behavior

- [ ] Rispetta l'obiettivo della feature.
- [ ] Non inventa dati.
- [ ] Mantiene Unknown.
- [ ] Distingue provenance.
- [ ] Distingue Health / Confidence / Data Quality.
- [ ] Fornisce evidence quando necessario.

## 2. Edge cases

- [ ] No sensors.
- [ ] Sensor unavailable.
- [ ] Sensor stale.
- [ ] Invalid value.
- [ ] Missing history.
- [ ] Empty cycle.
- [ ] Multiple bins.
- [ ] Restart/reload.

## 3. Home Assistant

- [ ] Config Flow/Options Flow corretti.
- [ ] Unique IDs stabili.
- [ ] Device association corretta.
- [ ] Entity naming/translations corrette.
- [ ] Availability corretta.
- [ ] No duplicate physical sensors.
- [ ] No event-loop blocking.
- [ ] Current HA conventions verified.

## 4. Testing

- [ ] Unit tests.
- [ ] Integration tests quando pertinenti.
- [ ] Regression test.
- [ ] Time-series tests.
- [ ] Multi-bin tests.
- [ ] Persistence/migration tests.
- [ ] Notification tests.

## 5. UX

- [ ] L'utente capisce lo stato.
- [ ] L'utente sa se deve agire.
- [ ] L'azione primaria è chiara.
- [ ] "Nothing to do" è possibile.
- [ ] "Why?" è accessibile.
- [ ] Unknown è spiegato.

## 6. Notifications

- [ ] Persistence.
- [ ] Cooldown.
- [ ] Deduplication.
- [ ] Recovery.
- [ ] Appropriate severity.

## 7. Automation

Se coinvolge hardware:

- [ ] opt-in;
- [ ] safe defaults;
- [ ] limits;
- [ ] timeout;
- [ ] cooldown;
- [ ] behavior on unknown/stale;
- [ ] manual override.

## 8. Documentation

- [ ] Documenti tecnici aggiornati.
- [ ] Guide utente aggiornata.
- [ ] README aggiornato.
- [ ] Changelog aggiornato.
- [ ] Known limitations documentate.

## 9. Release

- [ ] Clean install.
- [ ] Upgrade test.
- [ ] Restart test.
- [ ] No-sensor test.
- [ ] Sensor add/remove test.
- [ ] Multi-bin test.
- [ ] Batch/continuous test.
- [ ] Notification test.
- [ ] Translation test.
- [ ] Diagnostics test.
- [ ] HACS/GitHub requirements current check.

## 10. Final product question

Prima di dire "Done":

> Questa modifica rende Smart Compost Manager più utile, più preciso o più affidabile senza far credere al sistema di sapere ciò che in realtà non sa?

Se la risposta è no, la feature non è pronta.
