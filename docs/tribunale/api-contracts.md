# Tribunale del portafoglio — Contratto API, schemi dei dati, eventi SSE

Stato: **contratto di implementazione** per i lavori paralleli TASK-61…71. Ogni modulo deve
rispettarlo alla lettera; una deviazione va riportata in fondo a questo file (sezione
«Deviazioni», come in `docs/doctor2/api-contracts.md`), non decisa da sola.
Versione del contratto: **`tribunale-1.0`** (costante `CONTRACT_VERSION`).

Documenti collegati: architettura e proprietà dei file `docs/tribunale/architecture.md`,
specifica UI `docs/tribunale/ui-spec.md`, seduta di esempio
`docs/tribunale/fixtures/seduta-esempio.json` e lo stesso come stream
`docs/tribunale/fixtures/seduta-esempio.sse.txt`.

Il «Tribunale del portafoglio» è una sezione del Portfolio Doctor in cui tre voci AI con
filosofie d'investimento diverse discutono lo stesso portafoglio. Ogni affermazione poggia su
un dato calcolato dal Doctor. L'utente non riceve un verdetto né un consiglio: vede dove le
tre letture concordano e dove divergono, con il dato che sostiene ciascuna posizione.
**Il Doctor calcola, l'AI interpreta.**

## 0. Decisioni prese (non si ridiscutono)

- **Fascicolo**: elenco di fatti deterministici, ciascuno con id stabile (`F1`, `F2`…),
  etichetta, valore, unità, valore già formattato in italiano, fonte e qualità del dato.
  Nessun LLM lo produce (§4).
- **Voci** (id stabili): `indicizzatore` «L'indicizzatore» (basso costo, ampia
  diversificazione, semplicità), `fattoriale` «Il fattoriale» (inclinazioni volute,
  concentrazione consapevole), `prudente` «Il prudente» (protezione del capitale, reddito,
  tenuta nei ribassi) (§5).
- **Argomento**: oggetto strutturato con voce, tema, posizione (`punto_di_forza` /
  `criticita` / `neutro`), testo e id dei fatti citati. I numeri non si scrivono nel testo:
  si usano segnaposto `{F12}` che il backend sostituisce con il valore formattato (§6).
- **Seduta**: fascicolo → apertura (tre voci in parallelo) → replica (ogni voce risponde ad
  argomenti delle altre due) → sintesi (punti condivisi, punti contesi, domande aperte per
  l'utente). **Mai un vincitore.** Una seduta = 3 chiamate di apertura + 3 di replica + 1 di
  sintesi = 7 chiamate al modello (§8).
- **Verificatore** deterministico: un elemento che non supera i controlli viene scartato
  prima di arrivare all'utente; il frontend riceve **solo i conteggi** per voce e per codice,
  mai il testo scartato (§7).
- **Trasporto**: SSE come il Copilot (`data: {"type": ..., "content": ...}`), con eventi
  dedicati (§9).
- **Endpoint** sotto `/api/doctor/tribunal/...`, con lo stesso modo di indicare lo scope del
  Doctor 2.0 (§2).
- **Feature flag** `DOCTOR_TRIBUNAL_ENABLED` (default `true`), esposto in
  `GET /api/doctor/features` come `tribunal_enabled`.
- **Limite giornaliero** per chi usa la chiave del server; **riuso** della seduta salvata se
  l'hash del fascicolo è invariato (§8.6, §4.6).
- **Non è consulenza**: nessuna indicazione di comprare o vendere strumenti specifici; nessuno
  strumento che non sia già nel portafoglio viene nominato (`architecture.md` §8).

## 1. Costanti condivise

| costante | valore | definita in | note |
|---|---|---|---|
| `CONTRACT_VERSION` | `"tribunale-1.0"` | `services/tribunal/case_file.py` | entra nell'hash del fascicolo |
| `CASE_FILE_SCHEMA_VERSION` | `1` | `case_file.py` | |
| `MAX_FACTS` | `40` | `case_file.py` | fatti per fascicolo |
| `MIN_CITABLE_FACTS` | `6` | `case_file.py` | sotto → 409 `insufficient_data` |
| `MAX_INSTRUMENTS` | `30` | `case_file.py` | strumenti elencati nel fascicolo |
| `PROMPT_VERSION` | `"tribunale-prompt-1"` | `services/tribunal/personas.py` | da incrementare a ogni modifica dei prompt |
| `MAX_ARGUMENTS_PER_VOICE` | `4` | `services/tribunal/verifier.py` | argomenti ammessi per voce in apertura |
| `MAX_REBUTTALS_PER_VOICE` | `2` | `verifier.py` | repliche ammesse per voce |
| `MAX_FACTS_PER_ITEM` | `4` | `verifier.py` | fatti citati (distinti) per elemento |
| `MIN_TEXT_CHARS` | `20` | `verifier.py` | ogni testo |
| `MAX_ARGUMENT_CHARS` | `360` | `verifier.py` | testo di un argomento |
| `MAX_REBUTTAL_CHARS` | `280` | `verifier.py` | testo di una replica |
| `MAX_POINT_CHARS` | `300` | `verifier.py` | testo di un punto condiviso o conteso |
| `MAX_SIDE_CHARS` | `240` | `verifier.py` | `summary` di un lato di un punto conteso |
| `MAX_QUESTION_CHARS` | `200` | `verifier.py` | domanda aperta |
| `MAX_SHARED_POINTS` / `MAX_CONTESTED_POINTS` / `MAX_OPEN_QUESTIONS` | `3` / `3` / `3` | `verifier.py` | |
| `CALL_TIMEOUT_S` | `45` | `services/tribunal/orchestrator.py` | per tentativo di chiamata al modello |
| `SESSION_TIMEOUT_S` | `180` | `orchestrator.py` | seduta intera, dal primo byte |
| `HEARTBEAT_INTERVAL_S` | `10` | riuso da `copilot/streaming.py` | keepalive SSE |
| `DEFAULT_DAILY_LIMIT` | `3` | `app/config.py` (`doctor_tribunal_daily_limit`) | sedute al giorno con la chiave del server |

`personas.py` **non importa** `verifier.py` (i due task sono paralleli): i prompt riportano gli
stessi numeri come testo. TASK-71 aggiunge un test che confronta i numeri dei prompt con le
costanti del verificatore.

## 2. Scope e feature flag

Identico al Doctor 2.0 (`routes_doctor.py`, `docs/doctor2/api-contracts.md` §5):

- **GET**: `?portfolio_ids=19&portfolio_ids=26` (ripetuto), oppure `?portfolio_id=19`, oppure
  `?portfolio_ids=19,26`. Si riusano `_query_ids` e `DoctorRoute` di `routes_doctor.py`
  (importati, non modificati).
- **POST**: corpo `{"portfolio_ids": [19, 26], ...}` oppure `{"portfolio_id": 19, ...}`.
- Id deduplicati e ordinati, da 1 a 20; un id ≤ 0 o non numerico → 400 `invalid_request`.
- Un solo id = `scope_type: "single"`, più id = `"aggregate"`. `fingerprint = "p:" + id
  ordinati separati da virgola` (`scope.build_scope`). Oggetto `scope` nelle risposte =
  `PolicyScope` del Doctor: `{"portfolio_ids": [19], "scope_type": "single", "fingerprint": "p:19"}`.
- Proprietà verificata con `DoctorPolicyService.resolve_scope(ids, user_id)`: un portafoglio non
  posseduto → **404 `not_found`** (stesso errore e messaggio del Doctor, non rivela
  l'esistenza); valute base diverse → 400 `invalid_request`.
- Feature flag: `Settings.doctor_tribunal_enabled: bool = True` (env
  `DOCTOR_TRIBUNAL_ENABLED`), letto **a ogni richiesta**. Se `false` tutti gli endpoint
  `/doctor/tribunal/*` rispondono **404 `feature_disabled`**.
  `GET /api/doctor/features` (sempre attivo) diventa
  `{"policy_enabled": bool, "simulator_enabled": bool, "tribunal_enabled": bool}`.

Autenticazione e rate limit generale: `require_auth_rate_limited` su ogni endpoint, come il resto
del Doctor.

## 3. Endpoint

Prefisso `/api`. Tutti sotto `DoctorRoute` (errori di validazione → 400 `invalid_request` nel
formato del contratto).

| metodo | path | risposta |
|---|---|---|
| GET | `/doctor/tribunal/status?portfolio_ids=..` | `TribunalStatus` (JSON) |
| POST | `/doctor/tribunal/sessions` | `text/event-stream` (§9), oppure errore JSON prima dello stream |
| GET | `/doctor/tribunal/sessions/latest?portfolio_ids=..` | `TribunalLatestResponse` (JSON) |

### 3.1 `GET /doctor/tribunal/status`

Dice se il Tribunale è utilizzabile **con la configurazione Copilot dell'utente** e quante
sedute restano oggi. Non costruisce il fascicolo e non chiama il modello (risposta veloce).
Lo scope è obbligatorio e verificato (400/404 come sopra).

```json
{
  "available": true,
  "reason": null,
  "message": null,
  "provider": "openai",
  "model": "gpt-4o-mini",
  "key_source": "server",
  "limit": {"daily_limit": 3, "used_today": 1, "remaining": 2, "resets_at": "2026-11-10T23:00:00Z"},
  "scope": {"portfolio_ids": [19], "scope_type": "single", "fingerprint": "p:19"}
}
```

| campo | tipo | note |
|---|---|---|
| `available` | bool | `true` solo se si può avviare una seduta **nuova** adesso |
| `reason` | `null` \| `"copilot_not_configured"` \| `"provider_not_supported"` \| `"daily_limit_reached"` | `null` se `available` |
| `message` | str \| null | frase italiana per l'utente (testi in `ui-spec.md` §4) |
| `provider`, `model` | str \| null | della configurazione risolta (`null` se non configurato) |
| `key_source` | `"user"` \| `"server"` \| null | chi paga la chiamata (§8.6) |
| `limit` | oggetto \| null | solo con `key_source = "server"`; `null` con chiave propria o senza configurazione |
| `limit.resets_at` | str ISO UTC | prossima mezzanotte `Europe/Rome`, espressa in UTC con `Z` |
| `scope` | `PolicyScope` | |

Priorità di `reason`: `copilot_not_configured` → `provider_not_supported` → `daily_limit_reached`.
Con `daily_limit_reached` la seduta salvata resta consultabile e una richiesta di avvio con
fascicolo invariato viene comunque soddisfatta con la seduta salvata (§8.6): il frontend lo
sa leggendo `GET .../latest`.

### 3.2 `POST /doctor/tribunal/sessions`

Corpo:

```json
{"portfolio_ids": [19], "force_new": false}
```

| campo | tipo | default | note |
|---|---|---|---|
| `portfolio_ids` / `portfolio_id` | list[int] / int | — | scope (§2) |
| `force_new` | bool | `false` | `true` = «Rifai la seduta»: ignora la seduta salvata anche a fascicolo invariato |

Campi extra o tipi errati → 400 `invalid_request` con `field_errors`.

Controlli **prima** di aprire lo stream, in questo ordine (il primo che fallisce risponde con
errore JSON, §3.4):

1. feature flag → 404 `feature_disabled`;
2. corpo e scope → 400 `invalid_request` / 404 `not_found`;
3. configurazione Copilot → 503 `copilot_unavailable` (nessuna) / 409 `provider_not_supported`
   (provider senza risposta strutturata, cioè `local`);
4. seduta già in corso per lo stesso utente (qualunque scope, nello stesso processo) → 409
   `session_in_progress`;
5. costruzione del fascicolo → 409 `empty_portfolio` (nessuna posizione investita) / 409
   `insufficient_data` (meno di `MIN_CITABLE_FACTS` fatti citabili);
6. riuso: se `force_new` è `false` e la seduta salvata per `(utente, fingerprint)` ha lo stesso
   `case_file.hash` e lo stesso `contract_version` → 200 SSE con la **riproduzione** della
   seduta salvata (§9.4), senza chiamare il modello né consumare il limite;
7. limite giornaliero (solo `key_source = "server"`) → 429 `daily_limit_reached`;
8. altrimenti → 200 SSE con la seduta dal vivo.

Risposta 200: `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control":
"no-cache", "X-Accel-Buffering": "no"})`, come `/copilot/chat`.

Dopo l'apertura dello stream gli errori arrivano **solo** come evento `error` (§9.3.10): lo
status HTTP resta 200.

### 3.3 `GET /doctor/tribunal/sessions/latest`

Ultima seduta **conclusa e salvata** per `(utente, fingerprint esatto)`.

```json
{
  "session": { "...": "TribunalSession (§8.7)" },
  "current_case_file_hash": "6717b0c12c6dbc1f0ef107b75528bf84ee90211ea8b47eb6b2b9fa7fe56d6b21",
  "data_changed": false
}
```

| campo | tipo | note |
|---|---|---|
| `session` | `TribunalSession` \| null | `null` se non c'è una seduta salvata |
| `current_case_file_hash` | str \| null | hash del fascicolo ricostruito **ora**; `null` se `session` è `null` o se il fascicolo oggi non è costruibile (portafoglio vuoto) |
| `data_changed` | bool \| null | `null` se `session` è `null`; altrimenti `current_case_file_hash != session.case_file.hash` (anche `true` quando il fascicolo non è più costruibile o `contract_version` è cambiato) |

Finché TASK-66 non è chiuso, TASK-65 registra l'endpoint con uno store nullo che risponde sempre
`{"session": null, "current_case_file_hash": null, "data_changed": null}`. Il frontend deve
comunque degradare senza errori se l'endpoint manca del tutto (404 senza `error.code`).

### 3.4 Errori HTTP

Formato esistente del Doctor: `{"error": {"code", "message", "details"}}` con
`details = {"field_errors": [...], "request_id": str, "retryable": bool, ...}` (helper
`error_details` di `services/doctor_policy/errors.py`, `request_id_of` di `routes_doctor.py`).

| code | status | endpoint | quando | `retryable` | `details` aggiuntivi |
|---|---|---|---|---|---|
| `invalid_request` | 400 | tutti | corpo non oggetto JSON, campi extra, tipi errati, scope malformato, valute miste | false | `field_errors` |
| `not_found` | 404 | tutti | un portafoglio dello scope non è dell'utente | false | — |
| `feature_disabled` | 404 | tutti | `DOCTOR_TRIBUNAL_ENABLED=false` | false | — |
| `copilot_unavailable` | 503 | POST | nessuna configurazione Copilot (stesso codice di `/copilot/chat`) | false | — |
| `provider_not_supported` | 409 | POST | provider senza risposta strutturata (`local`) | false | `provider` |
| `session_in_progress` | 409 | POST | l'utente ha già una seduta in corso | true | — |
| `empty_portfolio` | 409 | POST | nessuna posizione investita nello scope | false | — |
| `insufficient_data` | 409 | POST | fatti citabili < `MIN_CITABLE_FACTS` | false | `citable_facts`, `min_citable_facts` |
| `daily_limit_reached` | 429 | POST | sedute nuove oggi ≥ limite, chiave del server | false | `daily_limit`, `used_today`, `resets_at`; header `Retry-After` (secondi) |
| `rate_limited` | 429 | tutti | limitatore generale esistente (`rate_limit.py`) | — | invariato |

Messaggi (italiano, per l'utente): vedi `ui-spec.md` §4. I `message` non contengono mai dati
del fascicolo.

## 4. Fascicolo

### 4.1 Fatto (`Fact`)

| campo | tipo | note |
|---|---|---|
| `id` | str `^F[1-9][0-9]{0,2}$` | `F1`, `F2`… assegnati in ordine (§4.4), senza buchi |
| `key` | str | chiave semantica stabile (§4.3), unica nel fascicolo |
| `group` | enum | `composizione` \| `concentrazione` \| `costi` \| `salute` \| `esposizione` \| `stress` \| `scenari` \| `regole` |
| `label` | str ≤ 160 | etichetta italiana (può contenere cifre: non è testo del modello) |
| `value` | number \| str \| null | numero arrotondato a 4 decimali (`round(x, 4)`, `-0.0` → `0.0`); stringa per `unit = "text"`; `null` se mancante |
| `unit` | enum | `pct` (punti percentuali 0–100, o negativi per gli impatti) \| `score` (0–100) \| `count` \| `index` (base 100) \| `months` \| `text` |
| `formatted` | str ≤ 40 | valore già formattato in italiano (§4.5); `"N/D"` se `value` è `null` |
| `source` | enum | `doctor_metrics` \| `positions` \| `health_score` \| `health_alerts` \| `xray` \| `stress_test` \| `monte_carlo` \| `doctor_policy` |
| `quality` | enum | `ok` \| `partial` \| `stale` \| `missing` |
| `citable` | bool | se `false` nessun elemento può citarlo (§7) |
| `reason` | str \| null ≤ 300 | obbligatorio se `citable = false`; per `partial` spiega la stima |
| `subject` | str \| null ≤ 80 | strumento (symbol), paese o settore a cui il fatto si riferisce |
| `sensitive` | bool | `true` per `unit = "score"`: mascherato in Privacy Mode (`ui-spec.md` §8) |

Il fascicolo **non contiene importi in valuta** (nessun valore di mercato, nessun saldo): né il
modello né il frontend ricevono importi del portafoglio. Per questo `unit` non ha `money`.

Regole di qualità e citabilità (deterministiche, TASK-61):

| caso | `quality` | `citable` | `value` / `formatted` | `reason` |
|---|---|---|---|---|
| dato calcolato completo | `ok` | true | valore | null |
| `MetricValue.quality == "partial"` con `coverage_pct ≥ 80` | `partial` | true | stima puntuale | «Stima sul X% …; intervallo tra L% e U%.» quando `lower ≠ upper` |
| `MetricValue.quality == "partial"` con `coverage_pct < 80` o `null` | `partial` | **false** | stima puntuale | «Copertura insufficiente (X%).» |
| stress test con `method = "proxy"` | `partial` | true | valore | `methodology_note` o «Stima con proxy di classe…» |
| quote non aggiornate (`MetricValue.quality == "stale"`) | `stale` | **false** | valore | nota del Doctor sulle quote |
| dato assente (`value is None`, `missing`, scenario non calcolabile, `recovery_months` null) | `missing` | **false** | `null` / `"N/D"` | motivo |
| regola personale `UNKNOWN` | `partial` | **false** | `"non verificabile"` | `reason` della regola |

Un dato mancante non è **mai** rappresentato come zero.

Freschezza: i fatti delle metriche del registry (`metric.*`) prendono la qualità da
`MetricValue.quality`, quindi diventano `stale` (non citabili) quando il Doctor segnala quote non
aggiornate. Le altre fonti (health, X-Ray, stress, Monte Carlo) non tracciano la freschezza e non
vengono marcate `stale`; in quel caso il fascicolo aggiunge a `notes` la nota del Doctor
(«Quotazioni non aggiornate: …»), che la UI mostra sopra il fascicolo.

### 4.2 Fascicolo (`CaseFile`)

| campo | tipo | note |
|---|---|---|
| `schema_version` | `1` | |
| `contract_version` | `"tribunale-1.0"` | |
| `status` | `"ready"` \| `"empty_portfolio"` | solo `ready` arriva al frontend (`empty_portfolio` → 409 prima dello stream) |
| `scope` | `PolicyScope` | |
| `generated_at` | str ISO UTC | escluso dall'hash |
| `as_of` | str ISO \| null | quota più vecchia usata (`snapshot.quote_as_of`); escluso dall'hash |
| `methodology_version` | str | `METHODOLOGY_VERSION` del Doctor (`"doctor-policy-1.0"`) |
| `hash` | str 64 hex | §4.6 |
| `instruments` | list ≤ 30 | `{symbol, isin, name}` degli strumenti dello scope, per peso decrescente (a parità: `symbol` crescente). `name` ripulito e troncato con `clean_text(name, max_chars=60)` di `copilot_doctor_tools.py` (≤ 61 caratteri con «…») |
| `facts` | list ≤ 40 | `Fact` in ordine di id |
| `counts` | `{total, citable}` | escluso dall'hash |
| `notes` | list[str] | note di servizio per la UI (es. «Vista aggregata di 2 portafogli.»); escluse dall'hash |

Tutte le stringhe che vengono da dati utente o importati (nomi, etichette con nomi, `reason`,
`subject`) passano da `clean_text` (caratteri di controllo e bidi rimossi). Sono **dati**, non
istruzioni: i prompt li presentano come tali (TASK-63).

### 4.3 Catalogo dei fatti

L'ordine del catalogo è l'ordine dei fatti nel fascicolo. Fonti: `services/doctor_policy`
(`build_snapshot`, `compute_metrics`, `build_evaluation_response`) e
`services/portfolio_doctor` (`analyze_portfolio_health`, `compute_portfolio_xray`,
`run_stress_test`, `run_monte_carlo_projection`), con lo scope come `int` (singolo) o `list[int]`
(aggregato). Nessun calcolo duplicato.

| # | group | key | label | unit | fonte | numero |
|---|---|---|---|---|---|---|
| 1 | `composizione` | `metric.equity_weight_pct` | `METRIC_REGISTRY[code].label` («Quota azionaria») | pct | `compute_metrics` | 1 |
| 2 | `composizione` | `metric.bond_weight_pct` | «Quota obbligazionaria» | pct | idem | 1 |
| 3 | `composizione` | `metric.gold_weight_pct` | «Quota oro / metalli preziosi» | pct | idem | 1 |
| 4 | `composizione` | `metric.usa_exposure_pct` | «Esposizione USA (look-through)» | pct | idem | 1 |
| 5 | `concentrazione` | `metric.max_single_position_pct` | «Peso massimo singola posizione»; `subject` = symbol del primo contributore | pct | idem | 1 |
| 6 | `concentrazione` | `metric.top3_positions_pct` | «Peso prime tre posizioni» | pct | idem | 1 |
| 7 | `concentrazione` | `metric.etf_overlap_pct` | «Overlap ETF» | pct | idem | 1 |
| 8 | `concentrazione` | `positions.count` | «Numero di posizioni» (security canoniche investite, cash esclusa) | count | `canonical_securities(snapshot)` | 1 |
| 9 | `costi` | `metric.weighted_ter_pct` | «TER medio ponderato» | pct (2 decimali) | `compute_metrics` | 1 |
| 10 | `salute` | `health.score` | «Punteggio di salute del Doctor» | score | `analyze_portfolio_health().score` | 1 |
| 11 | `salute` | `health.volatility_pct` | «Volatilità annua stimata del portafoglio» | pct | `.metrics.portfolio_volatility` | 1 |
| 12 | `salute` | `health.alert.<type>` | «Avviso del Doctor: » + `alert.message`; `value` = `"critico"` \| `"attenzione"` \| `"informativo"` (da `critical`/`warning`/`info`) | text | `.alerts` | ≤ 3, per severità (critical, warning, info) poi `type` crescente; un `type` ripetuto tiene il più severo |
| 13 | `esposizione` | `xray.coverage_pct` | «Copertura del look-through X-Ray» | pct | `compute_portfolio_xray().lookthrough_coverage_pct` | 1 |
| 14 | `esposizione` | `xray.country.<nome>` | «Esposizione per paese (parte scomposta): <nome>»; `subject` = nome | pct | `.aggregated_country_exposure` | ≤ 3 per peso decrescente (a parità: nome); «Non classificato» escluso dal top; se presente, la sua quota va nel `reason` di `xray.coverage_pct` («Non classificato: X%.») |
| 15 | `esposizione` | `xray.sector.<nome>` | «Esposizione per settore (parte scomposta): <nome>» | pct | `.aggregated_sector_exposure` | ≤ 3, come sopra |
| 16 | `stress` | `stress.<scenario_id>.impact` | «Stress test «<scenario_name>» (<period>): impatto stimato» | pct (negativo = perdita) | `run_stress_test()`, solo `scenario_type = "historical"` | 1 per scenario, nell'ordine di `HISTORICAL_SCENARIOS` |
| 17 | `stress` | `stress.<scenario_id>.recovery_months` | «Stress test «<scenario_name>» (<period>): mesi per il recupero» | months | idem | 1 per scenario, subito dopo il suo impatto |
| 18 | `scenari` | `mc.y<10\|20>.p<10\|50\|90>` | «Monte Carlo a 10 anni, 10° percentile (base 100)», «… mediana (base 100)», «… 90° percentile (base 100)» | index | `run_monte_carlo_projection().projections` (anno 10 e 20) | 6: y10 p10, p50, p90, poi y20 p10, p50, p90 |
| 19 | `regole` | `policy.failed_count` | «Regole personali violate» | count | `DoctorPolicyService.evaluate()` | 1, solo se esiste una policy per lo scope |
| 20 | `regole` | `policy.rule.<rule_id>` | «Tua regola «<label o label metrica>»: <label metrica>, <al minimo/al massimo/tra> <soglie>»; `value` = `"violata"` (FAIL) o `"non verificabile"` (UNKNOWN, non citabile) | text | `results` | ≤ 4, nell'ordine della evaluation; solo FAIL e UNKNOWN |

Un blocco che fallisce (eccezione nel servizio del Doctor) non fa fallire il fascicolo: i suoi
fatti compaiono come `missing` non citabili con `reason` «Dato non disponibile: <blocco> non
calcolabile.» (per righe a numero variabile — avvisi, paesi, settori, regole — il blocco
semplicemente non compare). Le 8 metriche del registry compaiono **sempre**.

Massimo teorico: 8 metriche + 1 posizioni + 2 salute (punteggio, volatilità) + 3 avvisi + 1
copertura X-Ray + 3 paesi + 3 settori + 8 stress (4 scenari × 2) + 6 Monte Carlo + 1 conteggio
regole + 4 regole = 40 = `MAX_FACTS`. Se una futura estensione supera il limite, si tolgono prima le righe a
numero variabile dal fondo di ciascun blocco, procedendo dall'ultimo gruppo (`regole`) al primo,
finché il totale è ≤ 40; le 8 metriche e `health.score` non si tolgono mai.

### 4.4 Id e ordine

I fatti sono costruiti nell'ordine del catalogo; le righe che non esistono (nessuna policy,
nessun avviso, meno di tre paesi) **non** generano fatti né lasciano buchi; poi si assegnano
`F1…Fn` in sequenza. A parità di dati di ingresso si ottengono gli stessi id, lo stesso ordine e
lo stesso hash.

### 4.5 Formattazione (`formatted`)

`formatted` è prodotto **solo** da `case_file.py` e consumato verbatim da verificatore e
frontend: nessun altro modulo riformatta un fatto.

| unit | regola | esempi |
|---|---|---|
| `pct` | `format_it(value, d) + "%"` (`doctor_policy/metrics.py`), `d = 2` per `metric.weighted_ter_pct`, `d = 1` per il resto; segno meno ASCII `-` | `46,6%`, `0,19%`, `-38,2%` |
| `score` | `f"{int(value)}/100"` | `71/100` |
| `count` | intero, separatore delle migliaia `.` sopra 999 | `6`, `1.204` |
| `index` | `format_it(value, 1)` | `158,7` |
| `months` | `"1 mese"` oppure `f"{int(value)} mesi"` | `49 mesi` |
| `text` | `value` così com'è (già ripulito) | `violata` |
| qualsiasi, `value is None` | `"N/D"` | |

### 4.6 Hash del fascicolo

```python
HASH_FACT_FIELDS = ("id", "key", "group", "label", "unit", "formatted", "source",
                    "quality", "citable", "reason", "subject", "sensitive")   # value escluso
payload = {
    "contract_version": cf["contract_version"],
    "schema_version": cf["schema_version"],
    "scope_fingerprint": cf["scope"]["fingerprint"],
    "methodology_version": cf["methodology_version"],
    "instruments": cf["instruments"],
    "facts": [{k: f[k] for k in HASH_FACT_FIELDS} for f in cf["facts"]],
}
data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
cf["hash"] = hashlib.sha256(data).hexdigest()   # 64 caratteri esadecimali minuscoli
```

Esclusi: `generated_at`, `as_of`, `counts`, `notes`, `hash`, `status` e, nei fatti, `value`
(l'hash segue `formatted`, cioè ciò che l'utente vede). Quindi una nuova quota che non cambia
nessun valore formattato né la qualità **non** cambia l'hash e la seduta salvata si riusa
(§8.6); un valore formattato, una qualità o una citabilità diversa lo cambiano. Il valore di
esempio della fixture (`6717b0c1…6b21`) è ricalcolabile con questo codice.

### 4.7 JSON Schema

`CaseFile` (Draft 2020-12; `Fact` è lo schema di `facts.items`):

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["schema_version", "contract_version", "status", "scope", "generated_at", "as_of",
               "methodology_version", "hash", "instruments", "facts", "counts", "notes"],
  "properties": {
    "schema_version": {"const": 1},
    "contract_version": {"const": "tribunale-1.0"},
    "status": {"enum": ["ready", "empty_portfolio"]},
    "scope": {
      "type": "object", "additionalProperties": false,
      "required": ["portfolio_ids", "scope_type", "fingerprint"],
      "properties": {
        "portfolio_ids": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 1, "maxItems": 20},
        "scope_type": {"enum": ["single", "aggregate"]},
        "fingerprint": {"type": "string", "pattern": "^p:[0-9]+(,[0-9]+)*$"}
      }
    },
    "generated_at": {"type": "string"},
    "as_of": {"type": ["string", "null"]},
    "methodology_version": {"type": "string"},
    "hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "instruments": {
      "type": "array", "maxItems": 30,
      "items": {
        "type": "object", "additionalProperties": false, "required": ["symbol", "isin", "name"],
        "properties": {
          "symbol": {"type": "string", "maxLength": 20},
          "isin": {"type": ["string", "null"]},
          "name": {"type": "string", "maxLength": 61}
        }
      }
    },
    "facts": {
      "type": "array", "maxItems": 40,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["id", "key", "group", "label", "value", "unit", "formatted", "source", "quality",
                     "citable", "reason", "subject", "sensitive"],
        "properties": {
          "id": {"type": "string", "pattern": "^F[1-9][0-9]{0,2}$"},
          "key": {"type": "string", "minLength": 1, "maxLength": 120},
          "group": {"enum": ["composizione", "concentrazione", "costi", "salute", "esposizione", "stress", "scenari", "regole"]},
          "label": {"type": "string", "minLength": 1, "maxLength": 160},
          "value": {"type": ["number", "string", "null"]},
          "unit": {"enum": ["pct", "score", "count", "index", "months", "text"]},
          "formatted": {"type": "string", "minLength": 1, "maxLength": 40},
          "source": {"enum": ["doctor_metrics", "positions", "health_score", "health_alerts", "xray", "stress_test", "monte_carlo", "doctor_policy"]},
          "quality": {"enum": ["ok", "partial", "stale", "missing"]},
          "citable": {"type": "boolean"},
          "reason": {"type": ["string", "null"], "maxLength": 300},
          "subject": {"type": ["string", "null"], "maxLength": 80},
          "sensitive": {"type": "boolean"}
        }
      }
    },
    "counts": {
      "type": "object", "additionalProperties": false, "required": ["total", "citable"],
      "properties": {"total": {"type": "integer"}, "citable": {"type": "integer"}}
    },
    "notes": {"type": "array", "items": {"type": "string"}}
  }
}
```

Esempio di fatto citabile e di fatto non citabile (dalla fixture):

```json
{"id": "F9", "key": "metric.weighted_ter_pct", "group": "costi", "label": "TER medio ponderato",
 "value": 0.19, "unit": "pct", "formatted": "0,19%", "source": "doctor_metrics", "quality": "ok",
 "citable": true, "reason": null, "subject": null, "sensitive": false}

{"id": "F24", "key": "stress.dotcom_crash.recovery_months", "group": "stress",
 "label": "Stress test «Dot-Com Crash» (2000-2002): mesi per il recupero", "value": null,
 "unit": "months", "formatted": "N/D", "source": "stress_test", "quality": "missing",
 "citable": false, "reason": "Tempo di recupero non disponibile per questo scenario.",
 "subject": null, "sensitive": false}
```

## 5. Voci e temi

### 5.1 `VoiceInfo`

```json
{"id": "indicizzatore", "code": "IND", "name": "L'indicizzatore", "mandate": "Basso costo, ampia diversificazione, semplicità."}
```

Ordine canonico (visualizzazione, riproduzione, totali): `indicizzatore`, `fattoriale`, `prudente`.

| id | code | name | mandate (testo esatto di `VoiceInfo.mandate`) |
|---|---|---|---|
| `indicizzatore` | `IND` | L'indicizzatore | «Basso costo, ampia diversificazione, semplicità.» |
| `fattoriale` | `FAT` | Il fattoriale | «Inclinazioni volute, concentrazione consapevole.» |
| `prudente` | `PRU` | Il prudente | «Protezione del capitale, reddito, tenuta nei ribassi.» |

### 5.2 Temi (`theme`)

Enum unico per tutte le voci: `costi`, `diversificazione`, `concentrazione`, `composizione`,
`esposizione_geografica`, `esposizione_settoriale`, `rischio`, `scenari`, `regole_personali`,
`qualita_dati`. Etichette italiane in `ui-spec.md` §6.

I «temi su cui si concentra» una voce orientano il prompt; **non** sono un controllo del
verificatore (un tema dell'enum fuori dal focus di una voce è ammesso).

### 5.3 Mandati, temi e divieti

| voce | mandato (nel prompt) | temi su cui si concentra | non può dire |
|---|---|---|---|
| L'indicizzatore | Legge il portafoglio con gli occhi di chi vuole replicare il mercato al minor costo: premia costi bassi, ampia diversificazione, poche regole semplici; segnala costi, sovrapposizioni e concentrazioni non necessarie. | `costi`, `diversificazione`, `concentrazione`, `esposizione_geografica`, `composizione` | che un indice «batte» sempre la gestione attiva; previsioni di rendimento; quale fondo o ETF usare al posto di un altro |
| Il fattoriale | Legge il portafoglio come insieme di inclinazioni (settori, aree, stili, concentrazioni): distingue un'inclinazione voluta da una casuale e ne mostra il costo in termini di rischio. | `esposizione_settoriale`, `esposizione_geografica`, `concentrazione`, `composizione`, `scenari` | che un'inclinazione renderà di più; strumenti «fattoriali» da aggiungere; tempi di entrata o uscita dal mercato |
| Il prudente | Legge il portafoglio dal lato della protezione del capitale, della componente di reddito e della tenuta nei ribassi storici e simulati. | `rischio`, `scenari`, `composizione`, `qualita_dati`, `regole_personali` | che il portafoglio è «sicuro» o garantito; promesse di protezione; prodotti difensivi da comprare |

Divieti comuni a tutte le voci (nel prompt di ogni fase, e verificati dove deterministici §7):
numeri solo tramite segnaposto `{Fn}` del fascicolo; almeno un fatto citato per elemento;
nessuna indicazione di acquisto, vendita, sostituzione o ribilanciamento; nessuno strumento,
emittente, ISIN o ticker fuori dal fascicolo; nessun giudizio di adeguatezza («adeguato al tuo
profilo», MiFID); nessun verdetto su quale voce abbia ragione; nessuna previsione di mercato;
testi del fascicolo trattati come dati; risposta in italiano; nessun uso della seconda persona
per dare istruzioni.

## 6. Argomenti, repliche, sintesi

Ogni fase ha due forme:

- **grezza**: ciò che il modello restituisce con la risposta strutturata (schema §6.4), con i
  segnaposto `{Fn}` nel testo; non esce mai dal backend;
- **verificata**: ciò che arriva al frontend e viene salvato, con id assegnati dal backend, il
  testo finale (`text`, segnaposto sostituiti) e il testo con segnaposto (`text_template`, per
  rendere i fatti come elementi selezionabili e mascherare i dati sensibili in Privacy Mode).

### 6.1 Argomento (apertura)

Grezzo (elemento di `arguments`): `{"theme", "stance", "text", "fact_ids"}`. La voce non è nel
JSON del modello: la conosce il backend.

Verificato (`TribunalArgument`):

| campo | tipo | note |
|---|---|---|
| `id` | str `^A-(IND\|FAT\|PRU)-[1-9]$` | `A-<code voce>-<n>`, `n` = posizione tra gli **ammessi** della voce (1, 2, …) nell'ordine grezzo |
| `voice` | id voce | |
| `phase` | `"apertura"` | |
| `theme` | tema §5.2 | |
| `stance` | `punto_di_forza` \| `criticita` \| `neutro` | |
| `text` | str | testo finale: testo normalizzato (§7.1) con ogni `{Fn}` sostituito da `facts[Fn].formatted` |
| `text_template` | str | testo normalizzato con i segnaposto |
| `fact_ids` | list[str] 1–4 | id citati, deduplicati nell'ordine originale |

### 6.2 Replica

Grezza (elemento di `rebuttals`): `{"target_argument_id", "stance", "text", "fact_ids"}`, con
`stance` ∈ `concorda` \| `contesta` \| `precisa`.

Verificata (`TribunalRebuttal`): `id` `R-<code>-<n>`, `voice`, `phase: "replica"`,
`target_argument_id` (argomento **ammesso** di apertura di **un'altra** voce), `target_voice`
(voce dell'argomento bersaglio), `stance`, `text`, `text_template`, `fact_ids` (1–4).

Partecipano alla replica solo le voci con almeno un argomento ammesso in apertura; ciascuna
riceve gli argomenti ammessi delle altre voci (con `text_template`, non il testo finale) e può
rispondere solo a quelli. Una replica non può rispondere a un'altra replica.

### 6.3 Sintesi

Il modello di sintesi riceve il fascicolo e gli elementi **già verificati** (argomenti e
repliche, con id e `text_template`), mai gli scartati. Grezza:

```
shared_points:    [{text, fact_ids, argument_ids}]
contested_points: [{text, fact_ids, sides: [{argument_ids, summary, fact_ids}, {…}]}]
open_questions:   [{text}]
```

`argument_ids` può contenere id di argomenti (`A-…`) e di repliche (`R-…`) ammessi.

Verificata (`TribunalSynthesis`):

```
shared_points:    [{id: "S<n>", text, text_template, fact_ids, argument_ids, voices}]
contested_points: [{id: "C<n>", text, text_template, fact_ids, metric_codes,
                    sides: [{voices, argument_ids, summary, summary_template, fact_ids}] (esattamente 2)}]
open_questions:   [{id: "Q<n>", text}]
```

- `voices` (di un punto condiviso o di un lato) è **derivato dal backend** dagli
  `argument_ids`, nell'ordine canonico delle voci; un punto condiviso ha almeno 2 voci; i due
  lati di un punto conteso hanno voci disgiunte.
- `metric_codes` è derivato dal backend: per i fatti citati dal punto e poi dai lati (in
  quest'ordine), le `key` che iniziano con `metric.` private del prefisso, senza duplicati
  (es. `["max_single_position_pct", "top3_positions_pct"]`). Serve a TASK-70 per la bozza di
  regola; vuoto se nessun fatto citato è una metrica del registry.
- Nessun campo indica un vincitore, un punteggio o una preferenza tra le voci.
- Le domande aperte non citano fatti e non hanno segnaposto.

### 6.4 Schemi inviati al modello

`personas.py` restituisce **esattamente** questi schemi (TASK-63), `structured.py` li riceve
così (TASK-62). Usano solo le parole chiave `type`, `properties`, `required`, `items`, `enum`,
`additionalProperties`, `minItems`, `minLength`, `description`. Volutamente **senza**
`maxItems`/`maxLength`: i limiti di quantità e lunghezza li applica il verificatore, così un
eccesso costa uno scarto (`troppi_argomenti`, `testo_troppo_lungo`) e non l'intera risposta.

`schema_name = "tribunal_opening"`:

```json
{
  "type": "object", "additionalProperties": false, "required": ["arguments"],
  "properties": {
    "arguments": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["theme", "stance", "text", "fact_ids"],
        "properties": {
          "theme": {"type": "string", "enum": ["costi", "diversificazione", "concentrazione", "composizione", "esposizione_geografica", "esposizione_settoriale", "rischio", "scenari", "regole_personali", "qualita_dati"]},
          "stance": {"type": "string", "enum": ["punto_di_forza", "criticita", "neutro"]},
          "text": {"type": "string", "minLength": 1},
          "fact_ids": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

`schema_name = "tribunal_rebuttal"`:

```json
{
  "type": "object", "additionalProperties": false, "required": ["rebuttals"],
  "properties": {
    "rebuttals": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["target_argument_id", "stance", "text", "fact_ids"],
        "properties": {
          "target_argument_id": {"type": "string"},
          "stance": {"type": "string", "enum": ["concorda", "contesta", "precisa"]},
          "text": {"type": "string", "minLength": 1},
          "fact_ids": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

`schema_name = "tribunal_synthesis"`:

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["shared_points", "contested_points", "open_questions"],
  "properties": {
    "shared_points": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false, "required": ["text", "fact_ids", "argument_ids"],
        "properties": {
          "text": {"type": "string", "minLength": 1},
          "fact_ids": {"type": "array", "items": {"type": "string"}},
          "argument_ids": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "contested_points": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false, "required": ["text", "fact_ids", "sides"],
        "properties": {
          "text": {"type": "string", "minLength": 1},
          "fact_ids": {"type": "array", "items": {"type": "string"}},
          "sides": {
            "type": "array", "minItems": 2,
            "items": {
              "type": "object", "additionalProperties": false, "required": ["argument_ids", "summary", "fact_ids"],
              "properties": {
                "argument_ids": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string", "minLength": 1},
                "fact_ids": {"type": "array", "items": {"type": "string"}}
              }
            }
          }
        }
      }
    },
    "open_questions": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false, "required": ["text"],
        "properties": {"text": {"type": "string", "minLength": 1}}
      }
    }
  }
}
```

`personas.py` può aggiungere `description` alle proprietà (non cambiano la validazione).
Una risposta non conforme allo schema è un errore della chiamata (`schema_mismatch`, §8.4), non
uno scarto.

### 6.5 JSON Schema degli oggetti verificati

`TribunalArgument`:

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["id", "voice", "phase", "theme", "stance", "text", "text_template", "fact_ids"],
  "properties": {
    "id": {"type": "string", "pattern": "^A-(IND|FAT|PRU)-[1-9]$"},
    "voice": {"enum": ["indicizzatore", "fattoriale", "prudente"]},
    "phase": {"const": "apertura"},
    "theme": {"enum": ["costi", "diversificazione", "concentrazione", "composizione", "esposizione_geografica", "esposizione_settoriale", "rischio", "scenari", "regole_personali", "qualita_dati"]},
    "stance": {"enum": ["punto_di_forza", "criticita", "neutro"]},
    "text": {"type": "string"},
    "text_template": {"type": "string"},
    "fact_ids": {"type": "array", "items": {"type": "string", "pattern": "^F[1-9][0-9]{0,2}$"}, "minItems": 1, "maxItems": 4}
  }
}
```

`TribunalRebuttal`:

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["id", "voice", "phase", "target_argument_id", "target_voice", "stance", "text", "text_template", "fact_ids"],
  "properties": {
    "id": {"type": "string", "pattern": "^R-(IND|FAT|PRU)-[1-9]$"},
    "voice": {"enum": ["indicizzatore", "fattoriale", "prudente"]},
    "phase": {"const": "replica"},
    "target_argument_id": {"type": "string", "pattern": "^A-(IND|FAT|PRU)-[1-9]$"},
    "target_voice": {"enum": ["indicizzatore", "fattoriale", "prudente"]},
    "stance": {"enum": ["concorda", "contesta", "precisa"]},
    "text": {"type": "string"},
    "text_template": {"type": "string"},
    "fact_ids": {"type": "array", "items": {"type": "string", "pattern": "^F[1-9][0-9]{0,2}$"}, "minItems": 1, "maxItems": 4}
  }
}
```

`TribunalSynthesis` (con `REF = {"type": "string", "pattern": "^[AR]-(IND|FAT|PRU)-[1-9]$"}`,
`FIDS = {"type": "array", "items": {"type": "string", "pattern": "^F[1-9][0-9]{0,2}$"}, "minItems": 1, "maxItems": 4}`,
`VOICE = {"enum": ["indicizzatore", "fattoriale", "prudente"]}`):

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["shared_points", "contested_points", "open_questions"],
  "properties": {
    "shared_points": {"type": "array", "maxItems": 3, "items": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "text", "text_template", "fact_ids", "argument_ids", "voices"],
      "properties": {
        "id": {"type": "string", "pattern": "^S[1-3]$"},
        "text": {"type": "string"}, "text_template": {"type": "string"}, "fact_ids": "FIDS",
        "argument_ids": {"type": "array", "items": "REF", "minItems": 2},
        "voices": {"type": "array", "items": "VOICE", "minItems": 2}}}},
    "contested_points": {"type": "array", "maxItems": 3, "items": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "text", "text_template", "fact_ids", "metric_codes", "sides"],
      "properties": {
        "id": {"type": "string", "pattern": "^C[1-3]$"},
        "text": {"type": "string"}, "text_template": {"type": "string"}, "fact_ids": "FIDS",
        "metric_codes": {"type": "array", "items": {"type": "string"}},
        "sides": {"type": "array", "minItems": 2, "maxItems": 2, "items": {
          "type": "object", "additionalProperties": false,
          "required": ["voices", "argument_ids", "summary", "summary_template", "fact_ids"],
          "properties": {
            "voices": {"type": "array", "items": "VOICE", "minItems": 1},
            "argument_ids": {"type": "array", "items": "REF", "minItems": 1},
            "summary": {"type": "string"}, "summary_template": {"type": "string"}, "fact_ids": "FIDS"}}}}}},
    "open_questions": {"type": "array", "maxItems": 3, "items": {
      "type": "object", "additionalProperties": false, "required": ["id", "text"],
      "properties": {"id": {"type": "string", "pattern": "^Q[1-3]$"}, "text": {"type": "string"}}}}
  }
}
```

(Le stringhe `"FIDS"`, `"REF"`, `"VOICE"` stanno per gli schemi definiti sopra.)

`DiscardSummary` (contenuto dell'evento `discarded`, §9.3.6):

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["phase", "voice", "admitted", "discarded", "by_code"],
  "properties": {
    "phase": {"enum": ["apertura", "replica", "sintesi"]},
    "voice": {"enum": ["indicizzatore", "fattoriale", "prudente", null]},
    "admitted": {"type": "integer", "minimum": 0},
    "discarded": {"type": "integer", "minimum": 0},
    "by_code": {"type": "object",
                "propertyNames": {"enum": ["<i codici di §7.3>"]},
                "additionalProperties": {"type": "integer", "minimum": 1}}
  }
}
```

`voice` è `null` solo per `phase = "sintesi"`. `by_code` ha solo i codici con conteggio ≥ 1,
in ordine alfabetico; `discarded` = somma di `by_code`.

## 7. Verificatore

Funzione pura (`verifier.py`, TASK-64): nessun accesso a rete, database, orologio o
configurazione; stesso ingresso → stessa uscita. Lavora su un elemento alla volta e restituisce
il **primo** codice di scarto nell'ordine di §7.3, oppure lo ammette.

### 7.1 Normalizzazione del testo

Prima di ogni controllo, a `text` (e a `summary`):

1. `clean_text(text, max_chars=10_000)` di `copilot_doctor_tools.py` (toglie caratteri di
   controllo, bidi, zero-width);
2. ogni sequenza di spazi bianchi (`\s+`, incluse le andate a capo) → un solo spazio;
3. `strip()`.

Il risultato è `text_template`; le lunghezze si misurano su di esso (`len()` Python = code
point). `text` = `text_template` con ogni segnaposto sostituito.

### 7.2 Segnaposto

- Segnaposto valido: regex `\{F([1-9][0-9]{0,2})\}` (esattamente `{F` + numero senza zeri
  iniziali + `}`; maiuscola, senza spazi).
- Dopo aver tolto i segnaposto validi, qualunque `{` o `}` residuo (es. `{F 12}`, `{f3}`,
  `{F012}`, `{FATTO}`) → `segnaposto_malformato`.
- I fatti «usati» da un elemento sono `fact_ids` ∪ id dei segnaposto: esistenza e citabilità si
  controllano su entrambi. Un fatto in `fact_ids` può non comparire come segnaposto (è citato
  come fonte senza mostrarne il valore).

### 7.3 Codici di scarto, in ordine di precedenza

| # | codice | si applica a | regola |
|---|---|---|---|
| 1 | `schema_non_valido` | tutti | campo mancante o di tipo errato, `theme`/`stance` fuori enum, testo normalizzato < `MIN_TEXT_CHARS`, `fact_ids` non lista di stringhe, punto conteso con un numero di lati ≠ 2 (difesa: lo schema della chiamata strutturata lo rende raro) |
| 2 | `riferimento_non_ammesso` | replica, sintesi | replica: `target_argument_id` non è un argomento **ammesso** di apertura o è della stessa voce; sintesi: un `argument_ids` non è un id ammesso (`A-…`/`R-…`), un punto condiviso con meno di 2 voci distinte, un lato senza `argument_ids`, due lati con una voce in comune |
| 3 | `nessun_fatto` | argomento, replica, punto, lato | `fact_ids` vuoto (dopo deduplicazione) |
| 4 | `troppi_fatti` | idem | più di `MAX_FACTS_PER_ITEM` (4) fatti distinti in `fact_ids` |
| 5 | `fatto_inesistente` | idem + domanda | un id in `fact_ids` o in un segnaposto non esiste nel fascicolo |
| 6 | `fatto_non_citabile` | idem | un id usato esiste ma ha `citable = false` |
| 7 | `segnaposto_malformato` | tutti | §7.2 |
| 8 | `segnaposto_non_citato` | tutti | un segnaposto valido punta a un fatto non presente in `fact_ids` (per le domande aperte, qualunque segnaposto) |
| 9 | `fatto_estraneo` | punti della sintesi | un fatto citato (dal punto o dai suoi lati) non è citato da nessuno degli elementi referenziati nel punto (`argument_ids` di tutti i lati per i contesi) |
| 10 | `testo_troppo_lungo` | tutti | lunghezza oltre il limite del tipo (§1) |
| 11 | `strumento_non_ammesso` | tutti | §7.5 |
| 12 | `cifra_libera` | tutti | §7.4 |
| 13 | `indicazione_operativa` | tutti | §7.6 |
| 14 | `verdetto` | tutti | §7.7 |
| 15 | `troppi_argomenti` | tutti | l'elemento supererebbe il massimo ammesso del suo tipo (§7.8) |

Per un punto conteso i controlli 3–14 si applicano al testo del punto e poi a ciascun lato
(`summary` con il limite `MAX_SIDE_CHARS`); il primo codice trovato scarta **tutto il punto**.
Le domande aperte saltano 3, 4, 9.

### 7.4 Cifre libere (`cifra_libera`)

Si applica al testo normalizzato **dopo** aver sostituito ogni segnaposto valido con uno spazio,
e dopo `unicodedata.normalize("NFKC", …)` (così `²`, `٣`, cifre a larghezza piena e `½` diventano
cifre ordinarie). È cifra libera, nell'ordine:

1. **Eccezioni rimosse prima del controllo** (sostituite da uno spazio):
   - un **identificativo di strumento del fascicolo** che contiene cifre (un `isin` o un
     `symbol` di `instruments`, o il `symbol` senza suffisso di borsa, es. `SXRV`), come token
     intero: `(?<![\w.])<id>(?![\w])`, maiuscole/minuscole esatte;
   - un **anno** `(?<![0-9])(19|20)[0-9]{2}(?![0-9])` solo se la stessa stringa di 4 cifre
     compare (con la stessa regex) nella `label` di almeno un fatto in `fact_ids`
     dell'elemento. Es.: «la crisi del 2008» è ammessa se l'elemento cita
     `stress.gfc_2008.impact` (label «… (2008): impatto stimato»); «nel 2030» non lo è mai.
2. qualunque carattere residuo con categoria Unicode `Nd`, `Nl` o `No` (cifre di ogni alfabeto,
   numeri romani Unicode, apici, frazioni) → `cifra_libera`. Quindi «top 3», «3 ETF», «10°»,
   «X-25» sono scartati;
3. qualunque simbolo residuo tra `%`, `‰`, `€`, `$`, `£`, `¥` → `cifra_libera` (anche senza
   cifre accanto);
4. **numerali in lettere**: si estraggono le parole con `re.findall(r"[^\W\d_]+", testo.lower())`
   (lettere Unicode, accenti inclusi); una parola è cifra libera se:
   - è in `QUANTITY_WORDS` = {`metà`, `doppio`, `doppia`, `doppi`, `doppie`, `triplo`,
     `tripla`, `decina`, `decine`, `dozzina`, `dozzine`, `centinaio`, `centinaia`, `migliaio`,
     `migliaia`, `milione`, `milioni`, `miliardo`, `miliardi`, `percento`}; oppure
   - corrisponde per intero (`re.fullmatch`) a `NUMERAL_RE` e **non** è in
     `ALLOWED_NUMERALS` = {`un`, `uno`, `una`, `due`, `tre`, `tré`, `sei`}.

   ```python
   U = r"(?:uno|un|una|due|tre|tré|quattro|cinque|sei|sette|otto|nove)"
   T = r"(?:dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove)"
   D = r"(?:venti|vent|trenta|trent|quaranta|quarant|cinquanta|cinquant|sessanta|sessant|settanta|settant|ottanta|ottant|novanta|novant)"
   S100 = rf"(?:{T}|{D}{U}?|{U})"
   C = rf"(?:(?:due|tre|quattro|cinque|sei|sette|otto|nove)?cento{S100}?)"
   S1000 = rf"(?:{C}|{S100})"
   NUMERAL_RE = re.compile(rf"(?:mille{S1000}?|{S1000}mila{S1000}?|{S1000})")
   ```

   Esempi: «le prime tre posizioni», «due voci», «una sola posizione» ammessi; «dieci anni»,
   «venti per cento», «vent'anni» (`vent`), «trentotto», «per cento» (`cento`), «metà del
   portafoglio», «il doppio» scartati. `sei` è ammesso perché coincide con il verbo «essere»
   (i prompt chiedono comunque di non usare la seconda persona). Gli ordinali («primo»,
   «secondo», «terzo», «quarto», «decennale») non sono numerali per questa regola.
   I numeri romani in lettere ASCII («XX») non sono trattati qui: un token maiuscolo di 2+
   lettere cade comunque nella regola dei ticker (§7.5).

Il valore di un segnaposto non è mai cifra libera (il segnaposto è tolto prima del controllo).
Gli id interni (`A-IND-1`, oppure `F12` senza graffe) non devono comparire nel testo: contengono
cifre e fanno scattare questa regola.

### 7.5 Strumenti fuori dal fascicolo (`strumento_non_ammesso`)

Sul testo come in §7.4 (segnaposto tolti, NFKC):

1. **ISIN**: ogni corrispondenza di `(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])` deve
   essere un `isin` di `instruments`;
2. **ticker**: ogni corrispondenza di `(?<![\w.])[A-Z][A-Z0-9]{1,5}(?:\.[A-Z]{1,3})?(?![\w])`
   deve essere un `symbol` di `instruments`, il suo prefisso prima del punto, oppure una sigla
   di `ALLOWED_ACRONYMS` = {`ETF`, `ETC`, `ETN`, `ETP`, `TER`, `OICR`, `UCITS`, `KID`, `ESG`,
   `REIT`, `PAC`, `ISIN`, `IPO`, `USA`, `UE`, `UK`, `EM`, `EUR`, `USD`, `GBP`, `CHF`, `JPY`,
   `PIL`, `BCE`, `FED`, `IVA`, `MSCI`, `FTSE`, `STOXX`, `NASDAQ`, `NYSE`, `DAX`, `BTP`, `BOT`,
   `CCT`, `AI`, `IA`}. Le parole in maiuscolo per enfasi sono quindi scartate (i prompt lo
   vietano);
3. **emittenti**: per ogni nome di `ISSUER_BRANDS` = {`ishares`, `vanguard`, `xtrackers`,
   `amundi`, `lyxor`, `spdr`, `invesco`, `wisdomtree`, `vaneck`, `hsbc`, `ubs`, `franklin`,
   `jpmorgan`, `j.p. morgan`, `fidelity`, `blackrock`, `pimco`, `dws`, `bnp paribas`, `deka`,
   `legal & general`, `l&g`, `global x`, `hanetf`, `state street`, `schwab`, `ossiam`, `fineco`,
   `eurizon`, `anima`, `arca`} presente nel testo minuscolo come parola intera
   (`(?<![\w])<nome>(?![\w])`), il nome deve comparire (sottostringa, minuscolo) in almeno un
   `name` di `instruments`.

### 7.6 Indicazioni operative (`indicazione_operativa`)

Sul testo minuscolo dopo NFKC, una corrispondenza di (parole intere):

```python
OPERATIVE_RE = re.compile(
    r"\b(?:compr(?:a|are|ate|i|iamo|ino|ando|erei|eresti|erebbe|erebbero)"
    r"|acquist(?:a|are|ate|i|iamo|ino|ando|erei|eresti|erebbe|erebbero)"
    r"|vend(?:i|ere|ete|iamo|a|ano|endo|erei|eresti|erebbe|erebbero)"
    r"|disinvest(?:i|ire|ite|iamo|a|ano|endo|irei|iresti|irebbe)"
    r"|liquid(?:are|ate|iamo|ando|erei|erebbe)"
    r"|sostitu(?:isci|ire|ite|iamo|isca|endo|irei|irebbe)"
    r"|allegger(?:isci|ire|ite|endo|irei|irebbe)"
    r"|ribilanci(?:a|are|ate|ando|erei|erebbe)"
    r"|switch(?:are)?"
    r"|consigli\w*|raccomand\w*|dovrest[ei]|devi|dovete|adeguat\w*|mifid)\b")
```

Copre l'acquisto/vendita/sostituzione di strumenti e il linguaggio prescrittivo o di
adeguatezza (radici vietate del Doctor 2.0, D09). Nota: «acquisti» come sostantivo e «liquidità»
(non corrisponde) sono trattati in modo diverso di proposito: il primo è scartato, il secondo no.

### 7.7 Verdetti (`verdetto`)

```python
VERDICT_RE = re.compile(
    r"\b(?:vince|vincono|vincitore|vincitrice|vincente|vincenti|perdente|perdenti|sconfitt\w*|verdetto"
    r"|ha ragione|hanno ragione|ha torto|hanno torto|la voce migliore|la tesi migliore)\b")
```

### 7.8 Limiti di quantità (`troppi_argomenti`)

Gli elementi si esaminano nell'ordine grezzo; un elemento che supera tutti i controlli 1–14 è
ammesso se gli ammessi del suo tipo sono meno del massimo, altrimenti è scartato con
`troppi_argomenti`. Massimi: apertura `MAX_ARGUMENTS_PER_VOICE` (4) per voce; replica
`MAX_REBUTTALS_PER_VOICE` (2) per voce; sintesi 3 punti condivisi, 3 contesi, 3 domande. Gli
scartati per altri motivi non occupano posto.

### 7.9 Uscita

Per ogni chiamata il verificatore restituisce gli ammessi (forma verificata §6, con id) e per gli
scartati solo `(indice nell'elenco grezzo, codice)`. Il testo scartato non lascia il
verificatore: non va negli eventi, nei log, nel salvataggio. I log riportano solo i codici
(TASK-65 AC #7).

## 8. Seduta

### 8.1 Fasi

```
fascicolo (deterministico) → apertura (3 voci in parallelo) → replica (voci valide in parallelo) → sintesi (1 chiamata)
```

| fase | chiamate | ingresso del modello | uscita verificata |
|---|---|---|---|
| `apertura` | 1 per voce, in parallelo | fascicolo | `TribunalArgument[]` per voce |
| `replica` | 1 per voce valida, in parallelo | fascicolo + argomenti ammessi delle altre voci | `TribunalRebuttal[]` per voce |
| `sintesi` | 1 | fascicolo + argomenti e repliche ammessi | `TribunalSynthesis` |

Ogni elemento ammesso viene inviato appena la chiamata della sua voce è stata verificata, senza
attendere le altre voci (le voci di una fase arrivano in ordine di completamento, non canonico).

### 8.2 Voci valide e fallimenti

- **Voce valida** = voce con almeno un argomento ammesso in apertura.
- Una voce che fallisce (errore della chiamata, §8.4) emette `voice_error`; una voce i cui
  argomenti sono tutti scartati emette `discarded` con `admitted: 0`. In entrambi i casi la
  seduta prosegue con le altre.
- Alla fine dell'apertura, **meno di 2 voci valide** → evento `error` `too_few_voices` e fine
  della seduta (nessun salvataggio).
- In replica partecipano solo le voci valide; una replica fallita o tutta scartata non ferma la
  seduta (la replica è opzionale).
- Sintesi fallita (errore della chiamata) → `error` `synthesis_failed`. Una sintesi verificata
  senza alcun punto (tutto scartato) è comunque una sintesi valida: evento `synthesis` con le
  tre liste vuote, seduta conclusa e salvata.

### 8.3 Prompt di sistema

La prima riga di ogni prompt di sistema è esattamente
`Tribunale del portafoglio — fase: <apertura|replica|sintesi>; voce: <id voce|sintesi>`
(serve ai finti LLM degli E2E e ai test; non contiene dati).

### 8.4 Chiamate al modello e timeout

- Ogni chiamata usa `copilot.structured.call_structured(config, system_prompt, messages, schema,
  schema_name=..., timeout_s=CALL_TIMEOUT_S)` (TASK-62).
- `call_structured` ripete **una sola volta** una risposta non conforme allo schema; poi solleva
  `StructuredOutputSchemaError`. Ogni tentativo ha il proprio `timeout_s`.
- Errori → `voice_error.code`: `StructuredOutputTimeout` → `timeout`,
  `StructuredOutputSchemaError` → `schema_mismatch`, `StructuredOutputProviderError` →
  `provider_error`, `StructuredOutputUnavailable` → `unsupported_provider` (non dovrebbe accadere:
  il controllo è prima dello stream).
- **Timeout di seduta** `SESSION_TIMEOUT_S` (180 s) dal primo byte: allo scadere le chiamate
  pendenti vengono abbandonate (i loro risultati ignorati), si emette `error` `timeout` e la
  seduta finisce (nessun salvataggio).
- Durante ogni attesa il backend invia `: keepalive\n\n` almeno ogni `HEARTBEAT_INTERVAL_S` (10 s),
  come `_run_with_heartbeat` del Copilot.
- Chiusura della connessione dal client: il generatore viene chiuso, le chiamate pendenti
  abbandonate, nulla viene salvato né conteggiato.

### 8.5 Concorrenza

Al massimo **una seduta in corso per utente** per processo (lock in memoria in
`orchestrator.py`): una seconda richiesta riceve 409 `session_in_progress`. Il lock si libera alla
fine dello stream, anche per errore o disconnessione.

### 8.6 Chiave, limite giornaliero e riuso

- `key_source = "user"` se l'utente ha `copilot_provider` e una chiave cifrata che si decifra
  (primo ramo di `resolve_copilot_config`); altrimenti `"server"` se il server è configurato.
  Funzione: `orchestrator.resolve_tribunal_config(settings, repo, user_id) -> TribunalConfig | None`.
- Provider con risposta strutturata: `openai`, `anthropic`, `gemini`, `openrouter`
  (`structured.STRUCTURED_OUTPUT_PROVIDERS`); `local` → `provider_not_supported`.
- **Limite**: `Settings.doctor_tribunal_daily_limit: int = 3` (env
  `DOCTOR_TRIBUNAL_DAILY_LIMIT`; `0` = Tribunale non disponibile con la chiave del server). Conta
  le sedute **dal vivo concluse e salvate** con `key_source = "server"` nel giorno di calendario
  `Europe/Rome` corrente, per utente (tutti gli scope). Riproduzioni, sedute fallite, interrotte o
  in timeout non contano. Con la chiave propria non c'è limite.
- Il controllo del limite all'avvio usa `used_today + sedute in corso dell'utente`; il limite
  può essere superato di al più una seduta solo con più processi backend (accettato).
- **Riuso**: avvio con `force_new = false` e seduta salvata dello stesso `(utente,
  fingerprint)` con `case_file.hash` e `contract_version` uguali → riproduzione (§9.4), anche se
  il limite è esaurito. `PROMPT_VERSION` e modello diversi **non** invalidano il riuso (l'utente
  può sempre chiedere «Rifai la seduta»).
- Si salva **solo l'ultima** seduta conclusa per `(utente, fingerprint)` (sovrascrive la
  precedente). Contenuti cifrati a livello di campo (`docs/field-encryption.md`), come gli altri
  dati personali (TASK-66). Eliminare un portafoglio dello scope o l'utente elimina le sedute.

### 8.7 Seduta salvata (`TribunalSession`)

È l'oggetto restituito da `GET .../latest` e la chiave `session` della fixture.

| campo | tipo | note |
|---|---|---|
| `session_id` | str `^trb_[0-9a-f]{16}$` | `"trb_" + secrets.token_hex(8)`, generato all'avvio |
| `scope` | `PolicyScope` | |
| `created_at` | str ISO UTC | avvio |
| `completed_at` | str ISO UTC | evento `done` |
| `contract_version` | str | |
| `prompt_version` | str | `PROMPT_VERSION` usata |
| `provider`, `model` | str | configurazione usata |
| `voices` | `VoiceInfo[]` | ordine canonico |
| `case_file` | `CaseFile` | quello della seduta |
| `arguments` | `TribunalArgument[]` | ordine canonico delle voci, poi id |
| `rebuttals` | `TribunalRebuttal[]` | idem |
| `synthesis` | `TribunalSynthesis` | |
| `discarded` | `DiscardSummary[]` | apertura (3 voci, ordine canonico), replica (voci valide), sintesi (1) |
| `voice_errors` | `VoiceError[]` | §9.3.7 senza `retryable` |
| `totals` | oggetto | `{arguments, rebuttals, shared_points, contested_points, open_questions, discarded}` |

`key_source` è salvato dallo store ma non esposto.

## 9. Eventi SSE

### 9.1 Formato

- Ogni evento è una riga `data: <json>` seguita da una riga vuota (`\n\n`), con
  `<json> = json.dumps({"type": <str>, "content": <oggetto>}, ensure_ascii=False)` su **una
  sola riga** (nessun `indent`).
- `content` è sempre un **oggetto JSON**, mai una stringa con JSON dentro (diversamente da
  `policy_draft` del Copilot, che è doppiamente codificato). Helper:
  `orchestrator.sse_event(event_type: str, content: dict) -> str`.
- Keepalive: riga di commento `: keepalive` + riga vuota, da ignorare.
- Il client legge come `CopilotChat.tsx`: accumula il buffer, divide su `\n`, considera solo le
  righe che iniziano con `data: `, fa `JSON.parse`; un evento malformato, con `type` sconosciuto
  o con `content` non oggetto si **ignora** senza interrompere la seduta.

### 9.2 Ordine (seduta dal vivo)

```
session
case_file
phase {apertura, started}
  per ogni voce, in ordine di completamento:
    argument × n   poi   discarded {apertura, voce}      oppure   voice_error {apertura, voce}
phase {apertura, completed}
  [se voci valide < 2: error {too_few_voices} e fine]
phase {replica, started}
  per ogni voce valida, in ordine di completamento:
    rebuttal × n   poi   discarded {replica, voce}       oppure   voice_error {replica, voce}
phase {replica, completed}
phase {sintesi, started}
  synthesis   poi   discarded {sintesi, null}            oppure   error {synthesis_failed} e fine
phase {sintesi, completed}
done
```

Garanzie per il frontend:

1. `session` è sempre il primo evento e `case_file` il secondo; `done` o `error` è sempre
   l'ultimo (esattamente uno dei due). Dopo `error` non arriva altro.
2. Ogni `argument`/`rebuttal` arriva tra il `phase started` e il `phase completed` della sua
   fase, prima del `discarded` della sua voce per quella fase.
3. Per ogni voce che partecipa a una fase arriva **esattamente uno** tra `discarded` e
   `voice_error`; per la sintesi esattamente uno tra (`synthesis` + `discarded`) ed `error`.
4. `error` `timeout` può arrivare in qualunque punto dopo `case_file`; ciò che è già arrivato
   resta valido.
5. Tra due eventi possono esserci zero o più keepalive.

### 9.3 Eventi

#### 9.3.1 `session`

```json
{"type": "session", "content": {
  "session_id": "trb_5f0c2a9e7d41b386",
  "scope": {"portfolio_ids": [19], "scope_type": "single", "fingerprint": "p:19"},
  "reused": false,
  "created_at": "2026-11-10T14:03:12Z",
  "contract_version": "tribunale-1.0",
  "prompt_version": "tribunale-prompt-1",
  "provider": "openai", "model": "gpt-4o-mini",
  "voices": [{"id": "indicizzatore", "code": "IND", "name": "L'indicizzatore", "mandate": "Basso costo, ampia diversificazione, semplicità."},
             {"id": "fattoriale", "code": "FAT", "name": "Il fattoriale", "mandate": "Inclinazioni volute, concentrazione consapevole."},
             {"id": "prudente", "code": "PRU", "name": "Il prudente", "mandate": "Protezione del capitale, reddito, tenuta nei ribassi."}]
}}
```

In riproduzione `reused: true` e `session_id`, `created_at`, `prompt_version`, `provider`,
`model` sono quelli della seduta salvata.

#### 9.3.2 `case_file`

`content` = `CaseFile` (§4.2) completo. Esempio: `session.case_file` della fixture.

#### 9.3.3 `phase`

```json
{"type": "phase", "content": {"phase": "apertura", "status": "started"}}
```

`phase` ∈ `apertura` \| `replica` \| `sintesi`; `status` ∈ `started` \| `completed`.

#### 9.3.4 `argument`

```json
{"type": "argument", "content": {
  "id": "A-IND-1", "voice": "indicizzatore", "phase": "apertura", "theme": "costi", "stance": "punto_di_forza",
  "text": "Il costo complessivo è contenuto: il TER medio ponderato è 0,19%, un livello coerente con una gestione passiva a basso costo.",
  "text_template": "Il costo complessivo è contenuto: il TER medio ponderato è {F9}, un livello coerente con una gestione passiva a basso costo.",
  "fact_ids": ["F9"]
}}
```

#### 9.3.5 `rebuttal`

```json
{"type": "rebuttal", "content": {
  "id": "R-FAT-1", "voice": "fattoriale", "phase": "replica",
  "target_argument_id": "A-IND-2", "target_voice": "indicizzatore", "stance": "contesta",
  "text": "Il peso di VWCE.DE non è una scommessa su un singolo titolo: il fondo è già diversificato e il punteggio di salute complessivo è 71/100.",
  "text_template": "Il peso di VWCE.DE non è una scommessa su un singolo titolo: il fondo è già diversificato e il punteggio di salute complessivo è {F10}.",
  "fact_ids": ["F10"]
}}
```

#### 9.3.6 `discarded`

Chiusura di una voce in una fase, con i conteggi (anche a zero).

```json
{"type": "discarded", "content": {"phase": "apertura", "voice": "prudente", "admitted": 3, "discarded": 2,
  "by_code": {"fatto_non_citabile": 1, "segnaposto_non_citato": 1}}}
```

Per la sintesi `voice: null` e `admitted` = punti condivisi + contesi + domande ammessi.

#### 9.3.7 `voice_error`

```json
{"type": "voice_error", "content": {"phase": "apertura", "voice": "fattoriale", "code": "timeout",
  "message": "Il fattoriale non ha risposto in tempo: la seduta prosegue con le altre voci.", "retryable": true}}
```

`code` ∈ `timeout` \| `schema_mismatch` \| `provider_error` \| `unsupported_provider`. `message`
in italiano, senza dettagli del provider né contenuti del fascicolo.

#### 9.3.8 `synthesis`

`content` = `TribunalSynthesis` (§6.3). Esempio ridotto:

```json
{"type": "synthesis", "content": {
  "shared_points": [{"id": "S1", "text": "Le voci concordano che il portafoglio è orientato alla crescita, con una quota azionaria di 75,6%.",
    "text_template": "Le voci concordano che il portafoglio è orientato alla crescita, con una quota azionaria di {F1}.",
    "fact_ids": ["F1"], "argument_ids": ["A-FAT-3", "R-PRU-1"], "voices": ["fattoriale", "prudente"]}],
  "contested_points": [{"id": "C1", "text": "Quanto pesa la concentrazione su VWCE.DE, che vale 46,6% del portafoglio.",
    "text_template": "Quanto pesa la concentrazione su VWCE.DE, che vale {F5} del portafoglio.",
    "fact_ids": ["F5"], "metric_codes": ["max_single_position_pct", "top3_positions_pct"],
    "sides": [
      {"voices": ["indicizzatore"], "argument_ids": ["A-IND-2", "R-IND-1"],
       "summary": "Per l'indicizzatore la diversificazione dipende troppo da pochi strumenti: le prime tre posizioni valgono 78,2%.",
       "summary_template": "Per l'indicizzatore la diversificazione dipende troppo da pochi strumenti: le prime tre posizioni valgono {F6}.",
       "fact_ids": ["F6"]},
      {"voices": ["fattoriale"], "argument_ids": ["A-FAT-2", "R-FAT-1"],
       "summary": "Per il fattoriale è una concentrazione consapevole su un fondo già diversificato, con 6 posizioni in tutto.",
       "summary_template": "Per il fattoriale è una concentrazione consapevole su un fondo già diversificato, con {F8} posizioni in tutto.",
       "fact_ids": ["F8"]}]}],
  "open_questions": [{"id": "Q1", "text": "Quanta oscillazione temporanea del valore saresti disposto ad accettare senza cambiare piano?"}]
}}
```

#### 9.3.9 `done`

```json
{"type": "done", "content": {"session_id": "trb_5f0c2a9e7d41b386", "reused": false, "saved": true, "duration_ms": 49210,
  "totals": {"arguments": 9, "rebuttals": 4, "shared_points": 2, "contested_points": 2, "open_questions": 2, "discarded": 7}}}
```

`saved` = `true` se la seduta è stata salvata (sempre `false` in riproduzione e con lo store
nullo); `duration_ms` = 0 in riproduzione.

#### 9.3.10 `error`

```json
{"type": "error", "content": {"code": "too_few_voices", "phase": "apertura", "retryable": true,
  "message": "Meno di due voci hanno prodotto argomenti verificabili: la seduta è stata interrotta. Riprova tra poco."}}
```

| code | quando | `retryable` |
|---|---|---|
| `timeout` | `SESSION_TIMEOUT_S` superato | true |
| `too_few_voices` | meno di 2 voci valide dopo l'apertura | true |
| `synthesis_failed` | la chiamata di sintesi è fallita | true |
| `internal_error` | eccezione inattesa nell'orchestratore | false |

`phase` = fase in corso (`null` se prima dell'apertura). Una seduta terminata con `error` non è
salvata e non consuma il limite.

### 9.4 Riproduzione di una seduta salvata

Stessa grammatica, senza keepalive, in **ordine canonico**: `session` (`reused: true`),
`case_file`, `phase apertura started`, per ogni voce in ordine canonico i suoi `argument` e poi il
suo `discarded`/`voice_error` salvato, `phase apertura completed`, lo stesso per la replica (voci
che vi hanno partecipato), `phase sintesi started`, `synthesis`, `discarded` della sintesi,
`phase sintesi completed`, `done` (`reused: true`, `saved: false`, `duration_ms: 0`). Il contenuto
di ogni evento è identico a quello salvato. Il frontend tratta allo stesso modo seduta dal vivo e
riproduzione.

## 10. Esempio completo (fixture)

`docs/tribunale/fixtures/seduta-esempio.json` contiene:

- `session`: la seduta conclusa (`TribunalSession`) su un portafoglio singolo (`p:19`) con 6
  strumenti e un fascicolo di 37 fatti (35 citabili; `F24` mancante e `F37` regola non
  verificabile); 9 argomenti, 4 repliche, sintesi con 2 punti condivisi, 2 contesi e 2 domande;
- `raw`: le risposte grezze del modello per ogni voce e fase, con i segnaposto `{Fn}`, inclusi 7
  elementi volutamente non validi;
- `expected_discards`: per ciascuno, fase, voce, posizione grezza e codice atteso
  (`cifra_libera`, `strumento_non_ammesso`, `fatto_non_citabile`, `segnaposto_non_citato`,
  `riferimento_non_ammesso`, due `indicazione_operativa`).

`docs/tribunale/fixtures/seduta-esempio.sse.txt` è la stessa seduta come stream dal vivo (30
eventi + keepalive, con le voci che completano in ordine non canonico).

Uso: TASK-63 e TASK-64 leggono la fixture da `docs/` come dato di test (fascicolo, risposte
grezze, scarti attesi); TASK-67 la copia senza modifiche in
`src/components/doctor/tribunal/fixtures/` e un test ne verifica l'uguaglianza con questa;
TASK-68 la usa per sviluppare l'interfaccia senza backend.

Estratto (apertura del prudente, dal grezzo al verificato):

```json
// raw.apertura.prudente.arguments[0] → session.arguments "A-PRU-1"
{"theme": "rischio", "stance": "criticita",
 "text": "In uno scenario come la crisi del 2008 il portafoglio avrebbe registrato un impatto stimato di {F21}, con un recupero stimato in {F22}: una tenuta debole nei ribassi profondi.",
 "fact_ids": ["F21", "F22"]}
// «2008» è ammesso perché compare nella label di F21; testo finale: «… impatto stimato di -38,2%, con un recupero stimato in 49 mesi: …»

// raw.apertura.prudente.arguments[4] → scartato, segnaposto_non_citato ({F10} non è in fact_ids)
{"theme": "rischio", "stance": "criticita",
 "text": "La volatilità annua stimata è {F11} e il punteggio di salute si ferma a {F10}.",
 "fact_ids": ["F11"]}
```

## Deviazioni

(Nessuna. I task che si discostano dal contratto aggiungono qui una sottosezione con il proprio
nome, come in `docs/doctor2/api-contracts.md`.)

### TASK-64

Nessuna deviazione dalle regole; alcune letture del testo dove il contratto lascia margine:

- **Punto conteso** (§7.3): i controlli 3–14 si eseguono codice per codice su punto e lati
  (prima il controllo 3 sul punto e su ciascun lato, poi il 4, …), così il codice restituito è
  sempre il primo nell'ordine di precedenza; `fatto_estraneo` guarda insieme i fatti del punto e
  dei lati. L'anno ammesso (§7.4) per un lato si cerca nelle label dei `fact_ids` del lato.
- **Domande aperte**: saltano solo 3, 4 e 9 (ultima frase di §7.3), quindi un segnaposto verso
  un fatto non citabile dà `fatto_non_citabile`; verso un fatto citabile `segnaposto_non_citato`.
- **Id interni nel testo** (§7.4, ultima frase): `F12` o `A-IND-1` scritti nel testo sono
  scartati, ma con `strumento_non_ammesso` (corrispondono alla regex dei ticker, controllo 11,
  che precede `cifra_libera`). In minuscolo (`a-ind-1`) restano `cifra_libera`.
- **Ticker** (§7.5.2): ammessi i `symbol` del fascicolo, il prefisso prima del punto di un
  `symbol` (es. `SXRV` per `SXRV.DE`) e `ALLOWED_ACRONYMS`; un ticker con un suffisso diverso
  (es. `EIMI.DE` quando il fascicolo ha `EIMI`) non è ammesso.
- Una lista grezza assente o non lista (`arguments`, `rebuttals`, punti, domande) è trattata
  come vuota (nessun ammesso, nessuno scarto): la forma della risposta la garantisce già
  `call_structured` (§6.4). Una voce sconosciuta solleva `ValueError`.

### TASK-63

Nessuna deviazione dalle firme né dagli schemi (gli schemi di §6.4 sono restituiti identici,
con sole `description` aggiunte). Precisazioni sul contenuto del messaggio `user`, coerenti con
`architecture.md` §2.1:

- il JSON tra `<fascicolo>` e `</fascicolo>` è `{"instruments": [...], "facts": [...], "notes": [...]}`:
  oltre ai campi previsti di fatti e strumenti include `notes` (es. la nota sulle quotazioni non
  aggiornate), trattate come dato; nel JSON `<`, `>` e `&` sono in escape `<`, `>`,
  `&`, così nessun valore può chiudere un marcatore;
- tra `<argomenti>` e `</argomenti>`: replica `{"arguments": [...]}`, sintesi
  `{"arguments": [...], "rebuttals": [...]}`; argomenti con `id, voice, theme, stance,
  text_template, fact_ids`, repliche con `id, voice, target_argument_id, target_voice, stance,
  text_template, fact_ids`; mai `text`;
- difesa in profondità: `build_rebuttal_request` esclude gli argomenti della voce stessa e
  `build_*` scartano gli elementi senza id verificato (`A-…`/`R-…`), ordinando per voce canonica
  e numero; i limiti del verificatore sono ripetuti in `personas.PROMPT_LIMITS` (per il test di
  confronto di TASK-71).

### TASK-61

Nessuna deviazione da nomi, tipi, ordine, formattazione e algoritmo di hash (il codice di §4.6
riproduce l'hash della fixture). Letture dove il contratto lascia margine:

- **Hash e nuove quote** (§4.6): risolto, l'hash esclude `value` e usa `formatted`, come dice il testo di §4.6.
- **`build_case_file`**: due parametri keyword-only in più, `finance_client=None` e
  `justetf_client=None`, passati a `compute_portfolio_xray` come nelle route del Doctor. Senza,
  l'X-Ray usa solo l'arricchimento salvato (TASK-65 può passarli).
- **Motivi delle metriche parziali**: «Stima sul X% del valore investito classificato; intervallo
  tra L% e U%.» (TER: «… del valore investito con TER noto.», senza intervallo perché manca il
  limite superiore); copertura assente → «Copertura insufficiente (N/D).». Metrica mancante:
  `reason` = l'ultima nota del Doctor che non riguarda le quote.
- **Stress test**: uno scenario con `method = "not_available"` o non restituito dal servizio
  produce entrambe le righe `missing` («Scenario non calcolabile per questo portafoglio.»), mai
  l'impatto `0.0` del servizio. Il tempo di recupero di uno scenario `proxy` eredita qualità
  `partial` e `reason` dell'impatto.
- **X-Ray**: nel `reason` di `xray.coverage_pct` va la quota «Non classificato» della
  distribuzione per paese; paesi e settori con peso ≤ 0 non entrano nel top.
- **Taglio a `MAX_FACTS`**: se anche le righe variabili non bastano, si tolgono le altre righe
  dal fondo con lo stesso ordine dei gruppi, sempre senza metriche e `health.score`.

### TASK-67

Nessuna deviazione dalle firme di `architecture.md` §3.1; solo aggiunte compatibili:

- `services/api/tribunal.ts` esporta anche `createTribunalSseParser(onEvent)` (parser incrementale
  usato dallo stream), `parseTribunalSseText(text)` (usato dalla fixture) e il tipo
  `StreamTribunalSessionOptions`; `tribunalTypes.ts` esporta anche `TribunalEventType`.
- `useTribunalSession.ts` esporta anche `sessionToReplayEvents(session)` (eventi della
  riproduzione §9.4); `sessionToState` è definito come la riduzione di quegli eventi.
- `fixtures/index.ts` esporta anche `tribunalSseFixtureText` e accetta in
  `createFakeTribunalResponse` l'opzione in più `pauseAfterEvents` (lo stream resta aperto dopo
  n eventi, per provare «Interrompi»); `failAfterEvents` fa fallire lo stream con `TypeError`.
- Errori lato client: uno stream che cade dopo almeno un evento → `stream_interrupted`; un
  errore di rete prima di qualunque evento → `network_error`; una risposta HTTP non 2xx senza
  `error.code` → `internal_error` (≥ 500) o `invalid_request` (4xx), con `retryable` da
  `details.retryable` se presente, altrimenti `status ≥ 500`.

### TASK-65

Nessuna deviazione da eventi, ordine, schemi, codici e status; solo aggiunte compatibili e
letture dove il contratto lascia margine:

- **Firme** (`architecture.md` §2.1): `TribunalOrchestrator.__init__` ha in più, keyword-only
  con default, `finance_client`, `justetf_client` (passati a `build_case_file`; `justetf_client`
  solo se `settings.justetf_xray_auto_enrich_enabled_resolved`, come `routes_copilot.py`),
  `case_file_builder` (default `build_case_file`), `clock`, `session_timeout_s`,
  `heartbeat_interval_s` (per i test). `register_tribunal_routes` ha in più `service_getter`,
  `finance_client`, `justetf_client` (usati solo per l'orchestratore di default, creato una
  volta alla prima richiesta). `orchestrator.py` esporta anche `TribunalError` (`AppError` con
  `headers`: la route lo rende con l'header `Retry-After`, che l'handler globale non supporta),
  `replay_session(session)` (§9.4), `next_rome_midnight(now)` e `DEFAULT_DAILY_LIMIT`.
- **Lock** (§8.5): insieme in memoria a livello di modulo (uno per processo, condiviso da tutte
  le istanze). Lo stream restituito da `start` libera il lock a fine stream, alla chiusura e
  anche se viene abbandonato senza essere mai letto. Poiché il controllo 4 precede il 7, al
  controllo del limite l'utente non ha altre sedute in corso nel processo: il termine «sedute in
  corso» di §8.6 vale 0 e si confronta `count_today` con il limite.
- **`voice_error.retryable`**: `false` solo per `unsupported_provider`. Un'eccezione inattesa
  (non `StructuredOutputError`) sollevata dalla chiamata al modello è trattata come
  `provider_error`; un'eccezione inattesa altrove (es. verificatore) → `error` `internal_error`.
- **`status`**: con chiave del server `limit` è presente anche quando `reason` è
  `provider_not_supported`; `remaining = max(0, daily_limit - used_today)` e
  `daily_limit_reached` quando `remaining = 0` (quindi sempre con limite `0`). I `message` sono i
  testi di `ui-spec.md` §4.1; quello di `daily_limit_reached` non contiene l'ora (la UI la
  ricava da `resets_at`).
- **`latest`**: lo scope è verificato anche con lo store nullo (400/404); il fascicolo è
  ricostruito solo se c'è una seduta salvata.
- **Salvataggio**: `done.saved` è `false` con lo store nullo o se `store.save` solleva (la seduta
  resta valida per l'utente, log con il solo nome dell'eccezione).
- **Log**: oltre a `tribunal.phase` e `tribunal.session` (con `codes=codice:n,…`,
  `error:<codice>` per una voce fallita, `-` se nessuno; `outcome` ∈ `completed`, `replay`,
  `too_few_voices`, `synthesis_failed`, `timeout`, `disconnected`, `internal_error`), una riga
  `tribunal.call phase=… voice=… error=<NomeClasse>` per ogni chiamata fallita.
- **Fuori dai file di TASK-65**: aggiungere il campo obbligatorio `tribunal_enabled` a
  `DoctorFeaturesRead` cambia la risposta di `GET /api/doctor/features`; l'asserzione di
  `tests/unit/test_doctor_policy_routes.py::test_features_reflect_flags` è stata aggiornata di
  conseguenza (due righe).

### TASK-68

Nessuna deviazione dalle props di `architecture.md` §3.2; letture dove `ui-spec.md` lascia margine:

- **Precedenza degli stati all'apertura** (§4): `unavailable` e `limit_reached` prevalgono sulla
  seduta salvata, che resta visibile sotto in sola lettura (`data-read-only="true"` sul
  contenuto, senza «Rifai la seduta» né slot `renderContestedActions`); con il Tribunale
  disponibile la seduta salvata dà `completed` con `data-source="saved"`.
- **Seduta salvata**: è mostrata da `sessionToState(latest.session)` senza chiamare `loadSaved`,
  così lo stato dell'hook resta `idle` e uno stato derivato dallo `status` (non disponibile,
  limite) non viene coperto. Lo stato risultante è identico.
- **Feature spenta** (`tribunal_enabled: false` o `404 feature_disabled` dallo status): la
  radice resta montata ma nascosta con `data-state="disabled"` (stato in più rispetto a §4,
  serve solo ai test; TASK-69 non mostra comunque la tab).
- **Errore dello status** (rete o HTTP): `data-state="error"` con «Riprova» che ripete la lettura.
  Un errore HTTP prima dello stream senza contenuto arrivato mostra sotto l'eventuale seduta
  salvata in sola lettura (senza la nota «Seduta incompleta»).
- **Stepper su mobile** (< 62em): le quattro etichette non entrano a 320–390px senza troncarsi;
  lo Stepper mostra solo i cerchi (con `aria-label` e `aria-current="step"`) e sotto la riga
  «Fase N di 4: <fase>» (o «Fasi completate: …»).
- **Schede mobili**: nome della voce su una riga, sotto pallino del colore e numero di argomenti
  (o `Loader`), per evitare troncamenti a 320px.
- File in più: `tribunalContext.ts` (contesto condiviso: fatti, voci, Privacy, resa compatta,
  navigazione verso una card). `TribunalFactChip.tsx` esporta anche `TribunalQualityBadge`;
  `TribunalVoices.tsx` esporta `buildVoiceViews` e `voiceOfCard`; `TribunalSection.tsx`
  esporta `TRIBUNAL_COMPACT_QUERY` e il tipo `TribunalSectionState`.
