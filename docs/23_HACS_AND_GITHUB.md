# 23 — HACS and GitHub

## 1. Obiettivo

Il repository locale deve essere pronto, dopo i test, per diventare un progetto pubblico.

La pubblicazione non è la prima fase.

## 2. Repository quality

Prima della pubblicazione:

- README;
- license;
- version;
- docs;
- changelog;
- custom component;
- tests;
- translations;
- issue/support guidance.

## 3. HACS

I requisiti HACS possono evolvere.

Prima di pubblicare, Cursor deve leggere i requisiti HACS correnti e adattare:

- repository structure;
- manifest;
- metadata;
- versioning;
- validation;
- release process.

Non affidarsi a una checklist storica.

## 4. GitHub

Prevedere:

```text
main
release tags
changelog
issues
```

e, se utile:

- feature request;
- bug report;
- support template.

## 5. Public README

Il README pubblico deve spiegare:

- cosa fa;
- cosa non fa;
- compatibilità;
- installazione;
- setup;
- sensori opzionali;
- entities;
- notifications;
- automations;
- limitations;
- troubleshooting.

## 6. Versioning

Versioni coerenti e leggibili.

## 7. Release gate

Non pubblicare finché non sono stati testati:

- zero sensor;
- temperature;
- moisture;
- multi-bin;
- cycles;
- notifications;
- restart;
- migration;
- translations;
- clean install.

## 8. Quality scale

Il progetto deve aspirare a livelli elevati di qualità Home Assistant, ma non dichiarare un livello raggiunto finché non sono soddisfatti i requisiti correnti.

Riferimento:

https://developers.home-assistant.io/docs/core/integration-quality-scale/

## 9. Current HA quality direction

La quality scale corrente considera, tra le altre cose:

- config flow;
- docs;
- entities;
- translations;
- devices;
- diagnostics;
- repairs;
- testing;
- strict typing per i livelli più avanzati.

I dettagli devono essere rivalidati prima della release.

## 10. Public support philosophy

I bug report devono richiedere solo informazioni utili:

- HA version;
- integration version;
- configuration summary;
- relevant logs;
- reproduction steps.

Mai chiedere credenziali.
