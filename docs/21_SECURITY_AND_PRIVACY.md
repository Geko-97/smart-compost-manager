# 21 — Security and Privacy

## 1. Principle

Il progetto deve funzionare localmente e raccogliere il minimo necessario.

## 2. No secrets in repository

Mai committare:

- tokens;
- API keys;
- passwords;
- private HA config;
- personal backups;
- `.env` con credenziali.

## 3. Logging

Non loggare:

- secret values;
- access tokens;
- authentication data.

Loggare invece:

- problemi di configurazione;
- sensori invalide;
- migration errors;
- unexpected domain conditions.

## 4. External dependencies

Servizi esterni devono essere opzionali e motivati.

Una eventuale futura integrazione cloud deve essere esplicita.

## 5. Diagnostics

Diagnostics devono essere sanitizzati.

## 6. Physical actions

Un comando fisico deve avere:

- opt-in;
- limiti;
- timeout;
- cooldown;
- fail-safe;
- manual override.

## 7. Unknown safety

Se un dato fondamentale è:

- Unknown;
- unavailable;
- stale;

una automazione fisica non dovrebbe agire automaticamente, salvo una policy sicura configurata esplicitamente dall'utente.

## 8. Data deletion

L'utente deve poter rimuovere i dati propri dell'integrazione secondo la strategia definita dal prodotto.

## 9. Multi-user HA

Non assumere che chiunque abbia accesso a Home Assistant debba poter cambiare impostazioni sensibili dell'integrazione.

Seguire i meccanismi di autorizzazione e visibilità di Home Assistant.
