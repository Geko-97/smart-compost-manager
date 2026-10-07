# 09 — Environment and Weather

## 1. Principio

Il compost vive in un ambiente.

Il motore deve conoscere l'ambiente quando disponibile, ma non deve confondere ambiente e compost.

## 2. Environment model

Per ogni bin:

```text
indoor/outdoor
rain_exposure
shelter
sun_exposure
ambient weather source
```

## 3. Weather inputs

Possibili:

- ambient temperature;
- ambient humidity;
- wind;
- current precipitation;
- forecast precipitation;
- forecast min/max;
- season.

## 4. Rain exposure

```text
none
partial
exposed
unknown
```

## 5. Sun exposure

```text
shade
partial
full_sun
unknown
```

## 6. Sheltering

```text
sheltered
semi_sheltered
exposed
unknown
```

## 7. Temperature delta

Quando sono disponibili temperature interna e ambientale:

```text
delta = compost_internal_temperature - ambient_temperature
```

Questo è un segnale interno utile.

## 8. Rain as prediction

Esempio:

```text
heavy rain forecast
+
exposed bin
```

→ aumentare il rischio di eccessiva umidità.

Se il bin non è esposto, la stessa pioggia può avere un peso minore.

## 9. Heatwave

Il sistema può aumentare il rischio di:

- drying;
- heat exposure;
- surface dehydration.

Non deve però sostituire misure interne con una temperatura esterna.

## 10. Season

La stagione deve essere derivata automaticamente.

L'utente non deve impostarla manualmente per forza.

## 11. No weather source

Senza weather:

- continuare a funzionare;
- environment variables sconosciute;
- non simulare il meteo.

## 12. Ambient humidity

Regola assoluta:

> ambient humidity ≠ compost moisture.

L'umidità ambientale può essere evidence ambientale, mai misura interna implicita.

## 13. Forecast and decision making

Il weather deve poter influenzare:

- raccomandazioni;
- risk;
- forecast;
- interpretation.

La sua influenza deve essere visibile quando cambia una decisione.
