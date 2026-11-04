# Doctor 2.0 — Contratti condivisi (Policy, Evaluation, Copilot, Scenario Lab)

Stato: **contratto di implementazione** per i lavori paralleli. Ogni modulo deve
rispettarlo alla lettera; eventuali deviazioni vanno riportate qui.
Il PRD di riferimento è "Valore365 — Portfolio Doctor 2.0" v1.0 (4 nov 2026).

Principi non negoziabili:
- Health Score standard (`app/services/portfolio_doctor/_health.py`) **invariato**.
- Nessuna funzione FIRE duplicata; nessuna formula finanziaria in TypeScript o nel LLM.
- Le metriche delle policy riusano le funzioni deterministiche già esistenti
  (`_holdings.py`, `_health.py`, `_xray.py`, `asset_classification.py`).
- `PASS` mai su dati UNKNOWN/stale, salvo bounds conservativi documentati.
- Copilot non salva mai: crea bozze e preview; il salvataggio richiede conferma UI
  con confirmation token monouso lato server. MCP esterno resta read-only.
- Scenario Lab non scrive mai su transazioni/posizioni.
- Feature flag backend: `doctor_policy_enabled` (default `true`),
  `doctor_simulator_enabled` (default `true`) in `app/config.py`
  (env `DOCTOR_POLICY_ENABLED`, `DOCTOR_SIMULATOR_ENABLED`). Se disabilitati gli
  endpoint rispondono 404 `feature_disabled`. Esposti al frontend da
  `GET /api/doctor/features` → `{"policy_enabled": bool, "simulator_enabled": bool}`.

## 1. Package backend

`src/backend/app/services/doctor_policy/`

| file | contenuto | owner |
|---|---|---|
| `metrics.py` | `METRIC_REGISTRY`, `MetricDefinition`, `MetricValue`, `compute_metrics(snapshot)` | core |
| `snapshot.py` | `DoctorSnapshot`, `build_snapshot(repo, portfolio_ids, user_id)`, `snapshot_from_holdings(...)` | core |
| `validator.py` | `validate_policy_document(doc) -> list[FieldError]`, `normalize_policy_document(doc)` | core |
| `evaluator.py` | `evaluate_policy(document, metrics, snapshot) -> PolicyEvaluation` | core |
| `templates.py` | template Bilanciato / Prudente / Dinamico (versionati, `TEMPLATE_VERSION`) | core |
| `scope.py` | `scope_fingerprint(ids)`, `scope_type(ids)` | core |
| `store.py` | persistenza (policy set, versioni, token), optimistic locking | persistence |
| `confirmation.py` | emissione/consumo token monouso | persistence |
| `service.py` | orchestrazione usata da REST e Copilot (load+evaluate, preview, save, restore) | persistence |
| `scenario.py` | Scenario Lab (simulatore puro) | lab |
| `cache.py` | cache in-memory TTL (evaluation/scenario) | persistence |

Schemi Pydantic: `src/backend/app/schemas/doctor_policy.py` (owner: core; gli altri
moduli aggiungono i propri modelli in fondo al file, in sezioni separate, oppure in
`app/schemas/doctor_scenario.py` per il Lab).

Route REST: `src/backend/app/api/routes_doctor.py` (`register_doctor_routes`), registrata in
`main.py` **prima** di `register_portfolio_health_routes`.

## 2. Metric registry (MVP: 8 metriche, codici allowlisted)

Tutte in unità `pct` (punti percentuali, 0–100). `METHODOLOGY_VERSION = "doctor-policy-1.0"`.

| metric_code | label | operatori | denominatore | fonte |
|---|---|---|---|---|
| `equity_weight_pct` | Quota azionaria | min, max, range | valore investito escluso cash | classificatore comune (`holding_asset_class == "equity"`) |
| `bond_weight_pct` | Quota obbligazionaria | min, max, range | valore investito escluso cash | idem (`bond`) |
| `gold_weight_pct` | Quota oro / metalli preziosi | min, max, range | valore investito escluso cash | idem (classe oro/commodity preziosi; documentare la mappatura) |
| `max_single_position_pct` | Peso massimo singola posizione | max | valore investito escluso cash | security canonica (ISIN, fallback asset_id) aggregata fra listing/portafogli |
| `top3_positions_pct` | Peso prime tre posizioni | max | idem | idem |
| `usa_exposure_pct` | Esposizione USA (look-through) | max, min, range | valore investito escluso cash | X-Ray / `compute_geographic_exposure`; quota non classificata esplicita → bounds |
| `weighted_ter_pct` | TER medio ponderato | max | universo coperto | `resolve_holding_ters`; coverage dichiarata |
| `etf_overlap_pct` | Overlap ETF | max | coppie di fondi | `compute_overlap_score` (misura diversa dalla concentrazione) |

Decisioni (D02, D03): cash escluso dai pesi asset class (cash non è una metrica MVP);
concentrazione per security canonica, overlap separato.

`MetricValue` (dataclass/Pydantic):
```
code: str
value: float | None          # valore puntuale non arrotondato (None se ignoto)
lower: float | None          # bound conservativo inferiore (look-through parziale)
upper: float | None          # bound conservativo superiore
unit: "pct"
coverage_pct: float | None   # 0-100, quota del denominatore classificata/coperta
quality: "ok" | "partial" | "stale" | "missing"
source: str                  # es. "asset_classification", "xray_lookthrough", "ter_registry"
denominator: str             # descrizione testuale del denominatore
denominator_value: float | None   # in valuta base
contributors: list[{symbol, name, isin, weight_pct}]  # max 10, ordinati per contributo
notes: list[str]
```

## 3. Documento policy (schema_version 1)

```json
{
  "schema_version": 1,
  "rules": [
    {
      "rule_id": "max-single",            // ^[a-z0-9][a-z0-9_-]{0,39}$, univoco
      "metric_code": "max_single_position_pct",   // allowlist; univoco nel documento
      "operator": "max",                  // "min" | "max" | "range"
      "min_value": null,                  // richiesto per min/range
      "max_value": 35.0,                  // richiesto per max/range
      "unit": "pct",
      "precision": 1,                     // 0..3 decimali per la UI
      "severity": "high",                 // "low" | "medium" | "high"
      "warning_margin": 2.0,              // pp; near_limit se entro margine dalla soglia
      "min_coverage_pct": 80.0,           // sotto → UNKNOWN (salvo bounds decisivi)
      "max_data_age_days": 5,             // età massima quote (giorni di calendario)
      "enabled": true,
      "label": "Max singolo ETF"          // opzionale, max 80 char
    }
  ]
}
```
Vincoli di validazione (`FieldError = {field, code, message}` con field tipo `rules[0].max_value`):
- max 20 regole; valori in [0, 100]; min ≤ max; operatori ammessi dal registry;
- unit deve essere quella del registry; no campi extra; no espressioni/eval;
- **fattibilità**: somma dei minimi di equity+bond+gold > 100 → errore `infeasible`
  (es. 55+50+10 = 115%); `top3 max` < `max_single max` → errore; `max_single max` * 3 < `top3 min`… (solo i casi certi);
- documento vuoto (0 regole) è valido.

Scope: `scope_fingerprint(ids) = "p:" + ",".join(sorted(set(ids)))`; `scope_type = "single" | "aggregate"`.
Policy aggregate indipendenti dalle singole; nessuna fusione fisica.

## 4. Evaluation

Stati: `PASS | FAIL | UNKNOWN | NOT_APPLICABLE | INACTIVE`; `near_limit` è booleano
addizionale (mai PASS automatico). Confronto su valori non arrotondati con
`EPSILON = 1e-9`; estremi inclusivi.

Regola dei bounds (look-through parziale): per `max`: PASS se `upper ≤ max`, FAIL se
`lower > max`, altrimenti UNKNOWN; per `min` simmetrico; per `range` combinazione.
Dati stale (quote più vecchie di `max_data_age_days` o sync fallita) → UNKNOWN con
`reason` esplicita, mai PASS. Coverage < `min_coverage_pct` e bounds non decisivi → UNKNOWN.
Portafoglio vuoto → stato risposta `empty_portfolio`, regole `NOT_APPLICABLE`.
Nessun documento → stato `no_policy`.

`RuleResult`:
```
rule_id, metric_code, label, operator, min_value, max_value, unit, precision, severity,
status, near_limit: bool,
actual: float|null, actual_lower: float|null, actual_upper: float|null,
breach_amount: float|null   // pp oltre la soglia violata (positivo), null se non FAIL
reason: str                  // frase italiana, es. "VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali"
coverage_pct, quality,
evidence: { source, denominator, denominator_value, contributors[], notes[],
            quote_as_of, calculated_at, methodology_version }
```
Ordinamento risultati: FAIL (severity desc, breach desc) → UNKNOWN → near_limit PASS → PASS → NOT_APPLICABLE → INACTIVE.

`PolicyEvaluationResponse`:
```
status: "ready" | "no_policy" | "empty_portfolio"
scope: { portfolio_ids: [..], scope_type, fingerprint }
policy_id: int|null, policy_version: int|null, policy_name: str|null
snapshot_id: str            // sha256 corto di posizioni+prezzi+classificazioni
snapshot_as_of: str|null    // timestamp quota più vecchia usata (ISO)
calculated_at: str (ISO UTC)
methodology_version: str
data_quality: { status: "ok"|"stale"|"partial"|"unknown", last_successful_price_sync, last_sync_status,
                stale_symbols: [..], missing_price_symbols: [..], oldest_price_at, note }
summary: { passed, failed, unknown, not_applicable, inactive, near_limit, total }
results: [RuleResult]
```

## 5. REST (prefisso `/api`)

Errori nel formato esistente `{"error": {"code", "message", "details"}}` dove
`details = {"field_errors": [...], "request_id": str, "retryable": bool}`.
Codici: `invalid_request`(400), `validation_error`(422 policy non valida),
`not_found`(404, anche scope non posseduto), `version_conflict`(409),
`confirmation_invalid`(409 token assente/scaduto/riusato/non corrispondente),
`feature_disabled`(404).

| metodo | path | note |
|---|---|---|
| GET | `/doctor/features` | flag |
| GET | `/doctor/metrics` | registry (code, label, unit, operators, denominator, description) |
| GET | `/doctor/templates` | template illustrativi |
| GET | `/doctor/policies?portfolio_ids=19&portfolio_ids=26` | policy dello scope esatto (anche `portfolio_id=26`). 200 `{policy: PolicyRead|null}` |
| POST | `/doctor/policies/validate` | body `{portfolio_ids, document}` → `{valid, field_errors, normalized_document}` |
| POST | `/doctor/policies/preview` | body `{portfolio_ids, document, base_version: int|null, source: "manual"|"copilot"|"template"}` → `PolicyPreviewResponse` |
| POST | `/doctor/policies` | body `{portfolio_ids, name, document, base_version, confirmation_token}` → `PolicyRead` (201) |
| GET | `/doctor/policies/{id}/versions` | lista versioni (diff, source, confirmed_at, actor) |
| POST | `/doctor/policies/{id}/restore` | body `{version_number, base_version}` → `PolicyRead` (nuova versione, source `restore`) |
| GET | `/doctor/evaluation?portfolio_ids=..` | `PolicyEvaluationResponse` |
| POST | `/doctor/scenarios/preview` | Scenario Lab, uno scenario |
| POST | `/doctor/scenarios/compare` | 2–3 scenari + attuale |

`PolicyRead`: `{id, name, scope: {...}, active, current_version, document, updated_at, created_at}`.

`PolicyPreviewResponse`:
```
valid: bool, field_errors: [...],
normalized_document, diff: [{rule_id, metric_code, change: "added"|"removed"|"modified", before, after}],
evaluation_before: PolicyEvaluationResponse|null,   // policy corrente
evaluation_after: PolicyEvaluationResponse,          // con la bozza, stesso snapshot
confirmation_token: str|null,                        // solo se valid
expires_at: str, base_version: int|null, document_hash: str
```
Token: monouso, TTL 15 min, legato a `(user_id, scope_fingerprint, document_hash, base_version)`,
salvato come sha256 in DB. `POST /doctor/policies` senza token valido → 409 `confirmation_invalid`.
Se `current_version != base_version` → 409 `version_conflict` (il vecchio salvataggio
non sovrascrive quello recente). Ogni read/write verifica la proprietà di tutti i
portafogli dello scope (max 20, deduplicati): un portafoglio rimosso o non più posseduto
rende la policy aggregata non leggibile (404).

## 6. Persistenza (migrazione `database/migrations/20261104_01_doctor_policies.sql`, copia in `src/backend/app/sql/migrations/create_doctor_policies.sql`, applicata all'avvio come le altre)

- `doctor_policy_sets(id bigserial pk, owner_user_id text, scope_type text, scope_fingerprint text, name text, active bool default true, current_version int, created_at, updated_at, archived_at)`; unique `(owner_user_id, scope_fingerprint)` where `archived_at is null`.
- `doctor_policy_scope_members(policy_set_id fk, portfolio_id bigint, pk(policy_set_id, portfolio_id))` — **nessuna FK cascade su portfolios**.
- `doctor_policy_versions(id, policy_set_id fk, version_number int, schema_version int, constraints jsonb, document_hash text, source text, diff jsonb, confirmed_at timestamptz, actor_user_id text)`, unique `(policy_set_id, version_number)`.
- `doctor_confirmation_tokens(token_hash text pk, owner_user_id, scope_fingerprint, document_hash, base_version int null, expires_at, used_at)`.
- RLS attiva senza policy (solo backend), come le altre tabelle.
- Cache evaluation/scenario: in memoria (TTL) chiave `(user, fingerprint, policy_version, snapshot_id, methodology_version)`.

## 7. Copilot (tool interni)

Tool in `app/copilot_tools.py` (page_context `doctor`): `read_doctor_policy`,
`read_doctor_metrics`, `validate_policy_draft`, `preview_policy`,
`read_doctor_violations`, `build_doctor_scenario`, `compare_doctor_scenarios`.
Nessun tool salva. `preview_policy` restituisce la preview e un `draft_id`; lo streaming
emette un evento SSE `{"type": "policy_draft", "content": <json PolicyPreviewResponse + portfolio_ids>}`
che il frontend mostra come card con "Conferma e salva" (chiama `POST /doctor/policies`
con il token). Il token non viene mai passato al LLM (il tool result al modello lo omette).
Routing: domande capitale/rendita/pensione → link FIRE (`/fire`), ordini → Portfolio
(`/portfolio`). MCP: allowlist solo `read_doctor_policy`, `read_doctor_metrics`,
`read_doctor_violations`, `validate_policy_draft`, `build_doctor_scenario`,
`compare_doctor_scenarios`; `preview_policy` in `MCP_TOOL_EXCLUDED` (emette token).

## 8. Scenario Lab

Input `ScenarioRequest`:
```
portfolio_ids: [int], snapshot_id: str|null (se diverso dall'attuale → 409 snapshot_changed),
policy_version: int|null,
mode: "manual" | "new_cash_only" | "rebalance",
new_cash: float >= 0,
operations: [{symbol|asset_id, action: "buy"|"sell", amount: float>0}]   // manual
target_weights: {asset_id: pct}                                          // rebalance (pesi complessivi)
constraints: {no_sell: bool, max_turnover_pct: float|null, keep_equity_total: bool},
fee_model: {pct: float, fixed: float}, tax_model: "none" (MVP lordo, D07),
label: str
```
Output `ScenarioResult`: `feasible, infeasible_reason, before{metrics, evaluation_summary}, after{...},
changes[{asset_id, symbol, before_value, after_value, before_weight, after_weight, delta_value}],
warnings[], violations_resolved[], violations_new[], required_new_cash (formula no-sell),
total_before, total_after, cash_in, costs, methodology_version, snapshot_id, data_quality,
disclaimer: "Simulazione teorica; nessun ordine eseguito."`.
Formula no-sell: per ridurre il peso di H da H/V a p senza vendite: `max(0, H/p − V)`.
Invarianti: valore conservato senza flussi/costi; con cash esterno varia solo di cash−costi;
nessuna posizione negativa; nessuna scrittura su DB; deterministico a snapshot invariato.
Volatilità dopo scenario non stimabile → `N/D` motivato (mai riciclare quella corrente).
Aggregati: solo pesi complessivi, nessun ordine per conto.

## Deviazioni

### Core (§1–4: metriche, snapshot, validator, evaluator, schemi)

Metodologia completa: `docs/doctor2/financial-methodology.md`.

- **Firme**: `compute_metrics(snapshot, repo=None)` (repo opzionale: senza repo
  solo fallback deterministici `infer_ter`/`infer_region_profile`, `source`
  `ter_inferred`/`region_inference`); `evaluate_policy(document, metrics, snapshot, *, now=None)`;
  `build_snapshot(repo, portfolio_ids, user_id)` accetta sempre una lista (anche di 1 id) e
  solleva `ScopeError` (sottoclasse di `ValueError`) per lista vuota/>20/id ≤ 0 e
  `ValueError` per portafoglio non posseduto/valute miste.
  In più: `validate_and_normalize(doc) -> (normalized|None, errors)`,
  `normalize_policy_document` solleva `PolicyValidationError(errors)` se non valido,
  `build_evaluation_response(document|None, snapshot, metrics=None, *, repo=None, policy_id=None,
  policy_version=None, policy_name=None, now=None)`, `scope.build_scope(ids) -> PolicyScope`,
  `scope.normalize_scope_ids(ids)`, `templates.list_templates()` / `get_template(id)`,
  `metrics.metric_definitions()`.
- **Body REST**: in `ValidateRequest`/`PreviewRequest`/`SaveRequest` il campo `document` è
  `dict` libero: la validazione stretta la fa `validator.py` (errori `FieldError` con path
  `rules[0].max_value`, risposta 422 `validation_error`), non Pydantic.
- **Schemi aggiuntivi** in `app/schemas/doctor_policy.py`: `MetricContributor`, `MetricValueRead`,
  `PolicyReadEnvelope` (`{policy: PolicyRead|null}`), `PolicyVersionsResponse`, `TemplatesResponse`,
  `MetricsResponse`, `DoctorFeaturesRead`. `MetricDefinitionRead` ha anche `source`,
  `default_warning_margin`, `methodology_version`. `TemplateRead` = `{template_id, name, description,
  template_version, illustrative: true, disclaimer, document}`. `PolicyVersionRead` include anche
  `document` e `document_hash`. Nel `PolicyPreviewResponse` `evaluation_after`, `expires_at`,
  `document_hash` sono nullable (documento non valido → nessuna valutazione/token).
- **Default normalizzati di una regola**: `precision` 1 (TER 2), `severity` `medium`,
  `warning_margin` per metrica (2 pp; TER 0,05; overlap 5), `min_coverage_pct` 80,
  `max_data_age_days` 5 (ammessi 1–365), `enabled` true, `label` null (stringa vuota → null).
- **Validazione più stretta**: con `operator: "max"` un `min_value` non nullo è errore `not_allowed`
  (e viceversa per `min`). Il controllo «`max_single max` × 3 < `top3 min`» è implementato ma
  irraggiungibile (top3 ammette solo `max`). La fattibilità considera solo le regole attive.
  Codici errore: `required`, `invalid_type`, `invalid_format`, `invalid_value`, `out_of_range`,
  `extra_field`, `unknown_metric`, `invalid_operator`, `operator_not_allowed`, `not_allowed`,
  `min_gt_max`, `invalid_unit`, `duplicate`, `too_many_rules`, `too_long`,
  `unsupported_version`, `infeasible`, `inconsistent`.
- **`document_hash`** normalizza il documento (se valido) prima dello sha256 del JSON canonico.
- **`MetricValue`**: `value` con copertura parziale = quota nota / coverage × 100 (stima sulla parte
  classificata); i bounds restano `lower`/`upper`. TER parziale: `lower` = costo coperto / 100,
  `upper = null`. `etf_overlap_pct` con meno di 2 fondi = 0 con nota (non `missing`).
- **Empty portfolio**: le regole disattivate restano `INACTIVE` (non `NOT_APPLICABLE`).
- **Prezzi mancanti** (nessuna quota o `price_fallback = avg_cost`): `UNKNOWN` se la loro quota del
  valore investito supera `100 − min_coverage_pct`; `data_quality.status = partial`.
- **`data_quality.status = "unknown"`** per snapshot senza alcuna informazione di sync né di prezzo
  (snapshot simulati / di test).
- **`snapshot_id`**: 16 caratteri esadecimali.
- **Cash**: escluse le posizioni `asset_type = "cash"` e il saldo di cassa; un fondo monetario
  (classe `cash` del classificatore) resta nel denominatore ma fuori da azioni/obbligazioni/oro.

### Persistence (§5 REST, §6 persistenza, store/confirmation/service/cache)

Architettura: `docs/doctor2/architecture.md`.

- **Errori**: classi in `app/services/doctor_policy/errors.py` (nuovo file, non in tabella §1):
  `InvalidRequest` 400, `PolicyValidationFailed` 422, `NotFound` 404, `VersionConflict` 409,
  `ConfirmationInvalid` 409, `FeatureDisabled` 404, `NotImplementedYet` 501 (`not_implemented`,
  usato dai placeholder Scenario Lab). `details` = `{field_errors, retryable, request_id}`;
  `request_id` = header `X-Request-ID` del client se ben formato (`[A-Za-z0-9._-]{1,64}`),
  altrimenti uuid4 hex (il middleware esistente non genera request id). Il 409
  `version_conflict` aggiunge `details.current_version`.
- **Body malformati** (non oggetto JSON, tipi errati, >20 id, `version_number < 1`): 400
  `invalid_request` con `field_errors` (path stile `portfolio_ids[0]`), non il 422 generico di
  FastAPI. Query `portfolio_ids` non numerici → 400. Nei body è accettato anche `portfolio_id`
  singolo; in query anche `portfolio_ids=19,26`.
- **`POST /doctor/policies`** senza `confirmation_token` (o stringa vuota) → 409
  `confirmation_invalid` (prima della validazione Pydantic). Documento non valido → 422
  `validation_error` con `field_errors`. Ordine dei controlli: scope (400/404) → documento (422)
  → token (409 `confirmation_invalid`) → versione (409 `version_conflict`). Token consumato
  nella stessa transazione del salvataggio: se il salvataggio va in conflitto il token resta
  non usato (ma è comunque legato alla vecchia `base_version`).
- **`source` della versione**: preso dalla preview che ha emesso il token (colonna aggiuntiva
  `doctor_confirmation_tokens.source`, default `manual`); il `SaveRequest` non ha `source`.
  `doctor_confirmation_tokens.created_at` aggiunta. `doctor_policy_sets.name` not null
  (default applicativo "La mia policy"), `current_version` default 0 prima della prima versione.
- **Restore**: non richiede token (azione esplicita UI, mai Copilot); `base_version` obbligatoria
  di fatto (`null` con policy esistente → 409). Documento ripristinato rinormalizzato; diff
  calcolato rispetto alla versione corrente. Mantiene il nome della policy.
- **Preview**: `evaluation_before` = `null` se lo scope non ha policy; `evaluation_after` = `null`
  se la bozza non è valida (nessun token, `expires_at` null). Il token viene emesso anche se
  `base_version` non è quella corrente (il salvataggio poi risponde 409 `version_conflict`).
  `evaluation_after.policy_version` = `null` (bozza), `policy_id`/`policy_name` della policy
  corrente se esiste.
- **Versioni**: `GET /doctor/policies/{id}/versions` → `PolicyVersionsResponse`
  `{policy_id, current_version, versions: [...]}` in ordine decrescente; `actor` = user id.
- **Archiviazione**: `DoctorPolicyStore.archive()` esiste (libera lo scope), nessun endpoint REST.
- **Scenario Lab**: le route chiamano `DoctorPolicyService.preview_scenario(user_id, payload)` /
  `compare_scenarios(user_id, payload)` con il body grezzo (dict); per ora rispondono 501
  `not_implemented` finché l'agente lab non le collega a `scenario.py`.
- **Cache**: la chiave usa `policy_version = 0` quando lo scope non ha policy.
- **`schema.sql`** aggiornato con le 4 tabelle; `supabase_full_setup.sql` non è più mantenuto
  come schema completo (manca già TASK-54) e non è stato modificato.
