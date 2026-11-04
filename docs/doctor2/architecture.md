# Portfolio Doctor 2.0 — Architettura backend

Riferimenti: contratto `docs/doctor2/api-contracts.md`, metodologia
`docs/doctor2/financial-methodology.md`. Questo documento descrive come i pezzi
sono collegati; le regole finanziarie restano nella metodologia.

## 1. Componenti

| componente | file | responsabilità |
|---|---|---|
| Route REST | `src/backend/app/api/routes_doctor.py` | `register_doctor_routes`: auth (`require_auth_rate_limited`), feature flag, parsing dei body, formato errori con `request_id`. Nessuna logica di dominio. |
| Servizio | `app/services/doctor_policy/service.py` | `DoctorPolicyService`: orchestrazione condivisa da REST e Copilot (scope, lettura, validazione, preview, salvataggio, versioni, ripristino, evaluation con cache). |
| Store | `app/services/doctor_policy/store.py` | `DoctorPolicyStore`: query SQL (`sqlalchemy.text`) su `repo.engine`; optimistic locking. |
| Token di conferma | `app/services/doctor_policy/confirmation.py` | emissione e consumo atomico dei token monouso (solo sha256 in DB). |
| Cache | `app/services/doctor_policy/cache.py` | `TTLCache` in memoria, thread-safe, LRU con dimensione massima. |
| Errori | `app/services/doctor_policy/errors.py` | sottoclassi di `AppError` con i codici del contratto (§5). |
| Core deterministico | `snapshot.py`, `metrics.py`, `validator.py`, `evaluator.py`, `scope.py`, `templates.py` | snapshot del portafoglio, 8 metriche, validazione/normalizzazione documento, evaluation PASS/FAIL/UNKNOWN (owner: core). |
| Scenario Lab | `app/services/doctor_policy/scenario.py` | simulatore puro (owner: lab). Le route `/doctor/scenarios/*` delegano a `DoctorPolicyService.preview_scenario/compare_scenarios`. |
| Migrazione | `database/migrations/20261104_01_doctor_policies.sql` (+ copia `app/sql/migrations/create_doctor_policies.sql`) | 4 tabelle, RLS attiva senza policy; applicata anche all'avvio in `_apply_pending_migrations` (transazione separata). |
| Flag | `app/config.py` | `doctor_policy_enabled`, `doctor_simulator_enabled` (default `true`; env `DOCTOR_POLICY_ENABLED`, `DOCTOR_SIMULATOR_ENABLED`). |

In `app/main.py` il servizio è un singleton di processo
(`get_doctor_policy_service`), così REST e Copilot condividono la stessa cache
e un salvataggio REST invalida ciò che legge il Copilot. Le route `/doctor/...`
sono registrate dopo quelle aggregate e prima di
`register_portfolio_health_routes`.

## 2. Flusso dei dati

```
UI / Copilot
   │  portfolio_ids, documento bozza
   ▼
routes_doctor ──(auth, flag, parsing)──► DoctorPolicyService
                                            │ 1. normalize_scope_ids + repo.resolve_portfolio_scope
                                            │ 2. store.get_policy_set(user, fingerprint)
                                            │ 3. build_snapshot(repo, ids, user)  ── posizioni, prezzi, freschezza
                                            │ 4. compute_metrics(snapshot, repo)
                                            │ 5. build_evaluation_response(documento, snapshot, metriche)
                                            │ 6. (preview) diff_documents + issue_token
                                            │ 7. (save) consume_token + store.save_version  [una transazione]
                                            ▼
                                     PostgreSQL: doctor_policy_* , doctor_confirmation_tokens
```

Le uniche scritture sono sulle tabelle `doctor_policy_*` e
`doctor_confirmation_tokens`; transazioni, prezzi e portafogli sono solo letti
(verificato dai test di integrazione con conteggio righe prima/dopo).

## 3. Pipeline di evaluation (1–8)

1. **Scope** — id deduplicati e ordinati, 1..20 (`invalid_request` 400 altrimenti);
   `scope_fingerprint = "p:" + id ordinati`, `scope_type` single/aggregate.
2. **Autorizzazione** — `repo.resolve_portfolio_scope`: ogni portafoglio deve essere
   dell'utente (404 `not_found` altrimenti) e con la stessa valuta base (400).
   Ripetuta a ogni lettura/scrittura, anche per le policy raggiunte per id
   (versioni, ripristino) usando i membri salvati.
3. **Policy** — policy attiva dello scope esatto; le aggregate sono indipendenti
   dalle singole (nessuna fusione).
4. **Snapshot** — posizioni (singole o multi), prezzi più recenti, flag stale/
   prezzo mancante; `snapshot_id` = sha256 corto di posizioni+prezzi+classificazioni.
5. **Freschezza** — stato della sincronizzazione dati di mercato
   (`mcp_server.freshness.sync_status`); se la lettura fallisce la qualità degrada
   a `unknown`, l'evaluation non fallisce mai per questo.
6. **Metriche** — 8 metriche MVP dal registry, con coverage, bounds e qualità.
7. **Evaluation** — regole PASS/FAIL/UNKNOWN/NOT_APPLICABLE/INACTIVE con
   `near_limit`, motivazioni ed evidenze; mai PASS su dati stale/UNKNOWN.
8. **Risposta e cache** — `PolicyEvaluationResponse`; cache TTL in memoria.

## 4. Persistenza e concorrenza

- `doctor_policy_sets`: una riga attiva per `(owner_user_id, scope_fingerprint)`
  (indice unico parziale `where archived_at is null`); `current_version`.
- `doctor_policy_scope_members`: membri dello scope, **senza FK su `portfolios`**:
  cancellare un portafoglio non cancella la policy, che diventa illeggibile (404).
- `doctor_policy_versions`: storico immutabile (documento normalizzato in `constraints`
  jsonb, `document_hash`, `source` manual/copilot/template/restore, `diff`, `actor_user_id`).
- `doctor_confirmation_tokens`: hash sha256 del token, vincoli, scadenza, `used_at`,
  `source` della preview (finisce nella versione salvata).

Optimistic locking (`store.save_version`): `select ... for update` sulla riga del
set; se non esiste e `base_version` è `null` si crea (versione 1), se esiste e
`current_version != base_version` → `version_conflict` 409 con
`details.current_version`. Due creazioni concorrenti sono risolte dall'indice
unico (il perdente riceve 409). Il ripristino crea una nuova versione con il
documento di quella scelta (`source = restore`), con lo stesso locking.

## 5. Modello di sicurezza

- Autenticazione Clerk + rate limit (`require_auth_rate_limited`) su ogni endpoint.
- Autorizzazione per scope a ogni chiamata; una policy di un altro utente, o con un
  membro non più posseduto, risponde 404 (non rivela l'esistenza).
- Salvataggio solo con **token di conferma monouso**: emesso dalla preview di una
  bozza valida, TTL 15 minuti, legato a `(user_id, scope_fingerprint, document_hash,
  base_version)`; in DB solo lo sha256. Il consumo è un singolo
  `update ... where used_at is null and expires_at > now() ... returning`, nella stessa
  transazione del salvataggio: se il salvataggio fallisce (es. 409) il token resta
  valido, ma un token già usato, scaduto o emesso per un altro documento/scope/
  versione base dà `confirmation_invalid` 409.
- Il Copilot può solo validare e fare preview; non chiama mai `save`/`restore`.
  Il token non deve arrivare al LLM (il tool lo omette dal risultato al modello).
- RLS attiva senza policy sulle nuove tabelle: nessun accesso via API Supabase.
- Log: solo conteggi e latenze (dimensione scope, numero regole, versione, ms);
  mai valori finanziari, documenti o token.

## 6. Caching

`TTLCache` (60 s, max 512 voci) con chiave
`(user_id, fingerprint, policy_version, snapshot_id, methodology_version)`.
Lo snapshot viene ricostruito a ogni richiesta, quindi prezzi o posizioni nuove
cambiano `snapshot_id` e mancano la cache: la cache evita solo il ricalcolo di
metriche ed evaluation sugli stessi dati. Un salvataggio o ripristino invalida tutte
le voci dello scope (`invalidate_scope`). La preview non usa la cache e calcola
prima/dopo sullo **stesso** snapshot e sulle stesse metriche.

## 7. Feature flag

| flag | endpoint interessati | se `false` |
|---|---|---|
| `doctor_policy_enabled` | `/doctor/metrics`, `/doctor/templates`, `/doctor/policies*`, `/doctor/evaluation` | 404 `feature_disabled` |
| `doctor_simulator_enabled` | `/doctor/scenarios/preview`, `/doctor/scenarios/compare` | 404 `feature_disabled` |

`GET /api/doctor/features` è sempre attivo e restituisce
`{"policy_enabled": bool, "simulator_enabled": bool}`. I flag sono letti a ogni
richiesta.

## 8. Test

- Unit (fake): `tests/unit/test_doctor_policy_routes.py`, `tests/unit/test_doctor_policy_service.py`.
- Integrazione su PostgreSQL 16 reale: `tests/integration/test_doctor_policy_postgres.py`
  con il cluster temporaneo di `tests/integration/conftest.py` (fixture `pg_engine`,
  saltata se i binari mancano; da root usa `runuser -u postgres`). Avvio:
  `cd src/backend && python -m pytest -q tests/integration/test_doctor_policy_postgres.py`
  (variabili opzionali `PG_BIN`, `PG_TEST_PORT`).
