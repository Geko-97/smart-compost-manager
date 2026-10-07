# 20 — Testing

## 1. Obiettivo

I test non servono solo a evitare regressioni: devono dimostrare le invarianti del prodotto.

## 2. Test levels

```text
Pure unit
→ domain
→ engine
→ Home Assistant integration
→ config flow
→ entities
→ persistence/migration
→ end-to-end/manual Docker
```

## 3. Critical test: zero sensors

Given:

```text
no sensors
```

Then:

- no fake measurements;
- temperature Unknown;
- moisture Unknown;
- system still useful;
- confidence reduced;
- data quality reduced.

## 4. Critical test: sensor added

Given:

```text
temperature sensor assigned
```

Then:

- thermal capability enabled;
- derived phase can improve;
- no duplicate temperature sensor created.

## 5. Critical test: sensor removed

Then:

- temperature capability becomes unavailable/unknown;
- phase confidence can decrease;
- no crash;
- other features continue.

## 6. Provenance tests

Assert:

- measured is not rewritten as estimated;
- estimated is never presented as measured;
- inferred diagnosis stores evidence;
- unknown remains unknown.

## 7. Ambient/internal separation

Test explicitly:

```text
ambient humidity = 90%
```

does not become:

```text
internal moisture = 90%
```

## 8. Multi-bin tests

Create:

```text
Bin A
Bin B
```

Send events to A and assert B is unchanged.

Repeat for:

- sensors;
- materials;
- observations;
- cycles;
- notifications;
- learning.

## 9. Time-series tests

Test:

- rise;
- peak;
- cooling;
- stagnation;
- recovery;
- new activity cycle.

## 10. Noise tests

Test transient spikes and ensure they do not generate unstable phase/diagnostic transitions.

## 11. Notification tests

Test:

- persistence;
- cooldown;
- deduplication;
- recovery;
- severity;
- no repeated spam.

## 12. Persistence tests

Test:

- restart;
- reload;
- migration;
- corrupt input;
- deletion.

## 13. Config tests

Test:

- first setup;
- skip sensors;
- add sensor;
- remove sensor;
- multiple bins;
- reconfiguration;
- invalid configuration.

## 14. Translation tests

Check that all user-facing strings required by the integration are represented correctly in translation structures.

## 15. Coverage

Aim to cover all meaningful integration behavior. Per release targeting high Home Assistant quality standards, verify the current quality-scale requirements rather than relying on an old numeric target.

## 16. Bug → regression

Ogni bug importante corretto deve, quando appropriato, ricevere un test che impedisca il ritorno dello stesso comportamento.

## 17. Manual Docker acceptance

Prima della release:

- clean install;
- restart;
- reload;
- sensor unavailable;
- sensor restored;
- no sensors;
- one sensor;
- many sensors;
- multiple bins;
- notifications;
- cycles;
- translations;
- diagnostics.
