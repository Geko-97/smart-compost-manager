# 24 — Coding Rules

## 1. Questo documento non detta l'algoritmo

Il codice può essere strutturato liberamente.

Queste regole esistono per proteggere il comportamento del prodotto.

## 2. Domain first

La logica di compostaggio deve essere espressa in funzioni/modelli testabili senza HA.

## 3. No implicit defaults that fake reality

Bad:

```python
temperature = raw_temperature or 20.0
```

Better:

```text
temperature = Unknown
```

oppure un vero default solo se il significato è dichiarato e corretto per quel campo.

## 4. Magic numbers

Soglie, pesi e coefficienti devono avere una ragione.

Devono essere:

- centralizzati;
- nominati;
- documentati;
- testati.

## 5. Units

Normalizzare le unità prima dei calcoli.

La UI segue la configurazione/unità di Home Assistant.

## 6. Time

Usare date/time timezone-aware.

Centralizzare l'accesso al tempo quando serve ai test.

## 7. Types

Preferire modelli tipizzati.

Il domain model non deve diventare una grande mappa non documentata.

## 8. Error handling

Errori reali non devono essere silenziati.

Evitare:

```python
except Exception:
    pass
```

## 9. Logging

Non loggare ogni campione a livello info.

Usare debug per dettagli ad alta frequenza.

## 10. Translations

User-facing text deve essere localizzabile.

## 11. Entity architecture

Seguire le pratiche correnti di Home Assistant:

- stable unique IDs;
- translated names;
- entity descriptions quando appropriato;
- appropriate entity categories;
- coordinator patterns quando utili.

## 12. Performance

Minimizzare:

- polling duplicato;
- storage duplicato;
- state changes inutili;
- huge attributes;
- full history scans.

## 13. Scientific language in code

Il risultato deve dichiarare il proprio significato:

```text
Measured
Estimated
Inferred
Unknown
```

## 14. Safe actions

Una action fisica deve essere esplicitamente distinguibile da una recommendation.

## 15. Code review questions

Prima di chiudere una modifica:

1. può inventare dati?
2. può confondere ambientale e interno?
3. può mischiare due bin?
4. può creare duplicate sensors?
5. può generare spam?
6. può agire su un input stale?
7. è testata?
8. è traducibile?
9. è compatibile con le convenzioni HA correnti?
10. conserva la spiegabilità?
