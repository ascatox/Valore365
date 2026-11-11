# Auditor dei calcoli — Architettura e contratto

Riferimenti: catalogo delle regole `docs/auditor/rules.md` (id, condizioni, tolleranze, portafogli
di prova), mandato dell'agente settimanale `docs/auditor/agent-playbook.md`, JSON Schema in
`docs/auditor/schemas/report.schema.json`, esempio di report in
`docs/auditor/fixtures/report-example.json`.
Origine: audit MCP di novembre 2026 (`docs/audit-mcp-2026-11/`).

Questo documento è il **contratto comune** dei task TASK-73…82. TASK-73…78 vengono sviluppati in
parallelo da agenti che non si parlano: tutto ciò che due task si scambiano (firme, chiavi dei
`dict`, codici, nomi dei file, argomenti dei tool) è fissato qui. Chi ha bisogno di deviare lo
scrive in fondo, nella sezione «Deviazioni», con il motivo.

Principio: **l'Auditor verifica i numeri che vedono gli utenti, non quelli che il codice pensa di
produrre.** Le regole leggono solo l'output dei tool MCP, chiamati con la stessa funzione del
server (`run_tool_sync`), e confrontano numeri fra loro, con ricalcoli indipendenti o con tabelle
di riferimento approvate. Non correggono nulla e non scrivono nulla nei dati dei portafogli.

## 0. Decisioni prese (non si ridiscutono)

1. Le regole sono **funzioni pure** sul contesto: `check(ctx, scope) -> dict`. Leggono i dati solo
   tramite il contesto; non aprono connessioni, non importano il repository, non chiamano servizi.
2. Il contesto chiama i tool con `app.mcp_server.tools.run_tool_sync` e le dipendenze del server MCP
   (`ToolDependencies`: repository, `PerformanceService`, finance client), applica
   `sanitize_output` come fa il server prima di rispondere al client e **memoizza** ogni coppia
   (tool, argomenti) per tutta l'esecuzione. Due sole letture dirette, elencate in §5.4, coprono ciò
   che i tool non espongono.
3. `run_tool_sync` **non** passa da `_run_bounded`: l'Auditor non consuma la quota MCP degli utenti
   (né la quota generale né quella dei tool pesanti) e non occupa i loro slot di concorrenza.
4. Il finance client è **sempre offline** (§5.5): nessuna chiamata a Yahoo o justETF in CI, in
   produzione o nella sessione dell'agente. Gli esiti sono riproducibili e non dipendono dalla rete.
5. Scambio fra moduli con **`dict` JSON-serializzabili** conformi agli schemi di §4 (come nel
   Tribunale). I moduli delle regole **non importano nulla dal motore** (`registry`, `context`,
   `runner`, `report`): possono importare solo la libreria standard e costanti di riferimento
   dell'app elencate in §3.2. Così TASK-74…77 scrivono e testano le regole senza TASK-73.
6. I file delle regole (TASK-74…77) **non creano `__init__.py`**: prima che TASK-73 sia unito,
   `app/services/auditor/` e `rules/` funzionano come namespace package; gli `__init__.py` li crea
   solo TASK-73. Nessun task crea file di supporto condivisi nei test: ogni file di test copia il
   contesto finto di §10.
7. Esiti: `pass` / `fail` / `skip` / `error`. Una regola restituisce solo `pass`, `fail` o `skip`;
   `error` lo produce il motore (eccezione, timeout, errore di tool, esito non valido). Quando i dati
   non bastano la regola dà `skip` con un codice, **mai `pass`**.
8. Severità P0 / P1 / P2 con la semantica di §4.4. Codice di uscita della CLI: 0 / 1 / 2 (§3.6).
9. Privacy (§7): in CI l'evidenza contiene tutto (dati di prova); della corsa notturna in produzione
   si salvano solo id regola, esito, portafoglio, tipo di scope, severità e data.
10. Un difetto reale trovato da una regola non la disattiva: la regola resta e riceve
    `known_defect: "TASK-NN"` (TASK-79); un `fail` su una regola con difetto noto non cambia il
    codice di uscita, salvo `--strict-known`.

## 1. Flusso

```
                      ┌──────────── CLI: python -m app.services.auditor (CI, locale, agente)
                      │             endpoint interno POST /api/internal/auditor/run (notturna)
                      ▼
 build_tool_dependencies(offline=True) ──► ToolDependencies(repo, performance_service, OfflineFinanceClient)
                      │
 per ogni utente:  AuditContext(deps, user_id, run_id, mode)
                      │
 discover_scopes(ctx) ─► list_portfolios → scope portfolio (uno per portafoglio)
                      │                  → scope aggregate (per valuta base, 2-20 portafogli)
                      │                  → scope instrument (simboli di get_positions)
                      │                  → scope user (uno, con tutti i portafogli dell'esecuzione)
 load_rules() ───────► rules/stress_classification.py  (A, TASK-74)
                      │ rules/rebalance_simulation.py  (B, TASK-75)
                      │ rules/costs_income.py          (C, TASK-76)
                      │ rules/consistency.py           (D, TASK-77)
                      ▼
 run_audit(ctx, rules, options)
    per regola (ordine per id) × scope compatibile (ordine per scope_key):
       evaluate_rule ── thread con timeout ──► rule.check(ctx, scope)
                                                 └─ ctx.call / ctx.scoped / ctx.try_call ──► run_tool_sync (memo)
                                                 └─ ctx.transactions / ctx.performance_audit (memo)
       eccezione → error/exception · timeout → error/timeout · errore tool → error/tool_error
    ▼
 report (dict, schema §4.2) ──► JSON + Markdown (CI, locale, agente)
                            └─► privacy_rows(report) ──► store (solo notturna, §7)
```

L'unica scrittura dell'Auditor è lo storico degli esiti della corsa notturna (TASK-80). Le
simulazioni (`calculate_rebalance_orders`, `calculate_what_if`, `calculate_pac_contribution`) sono
calcoli in memoria: non scrivono.

## 2. Moduli backend — `src/backend/app/services/auditor/`

| file | task | responsabilità |
|---|---|---|
| `__init__.py` | 73 | solo docstring; **nessuna re-export**, nessun import pesante (importare una regola non deve caricare il motore né il DB) |
| `registry.py` | 73 | costanti condivise, `Rule`, validazione delle dichiarazioni, caricamento e filtro delle regole |
| `context.py` | 73 | `AuditContext`, memoizzazione, `scoped_tool_args`, letture dirette, `OfflineFinanceClient`, `build_tool_dependencies`, `discover_scopes` |
| `runner.py` | 73 | `RunOptions`, `evaluate_rule`, `run_audit`, `exit_code_for` |
| `report.py` | 73 | costruzione del report, JSON, Markdown, validazione, `privacy_rows` |
| `report_schema.json` | 73 | copia identica di `docs/auditor/schemas/report.schema.json` (un test ne verifica l'uguaglianza) |
| `__main__.py` | 73 | CLI |
| `rules/__init__.py` | 73 | solo `RULE_MODULES` (tupla dei nomi dei moduli dei gruppi); nessun import eager |
| `rules/stress_classification.py` | 74 | gruppo A |
| `rules/rebalance_simulation.py` | 75 | gruppo B |
| `rules/costs_income.py` | 76 | gruppo C |
| `rules/consistency.py` | 77 | gruppo D |
| `offline_returns.py` | 77 | ricalcolo indipendente di TWR e XIRR, spostato da `scripts/audit/twr_mwr_offline_auditor.py` (solo libreria standard) |
| `store.py` | 80 | storico degli esiti della corsa notturna, lock, orchestrazione multiutente |

Altri file backend: `api/routes_auditor_internal.py` (TASK-80: endpoint interni con token ed
endpoint amministrativo), `api/routes_auditor_user.py` (TASK-81: endpoint utente in sola lettura),
registrazione in `main.py` e impostazioni in `config.py` (TASK-80).

## 3. Firme pubbliche

Le firme sono vincolanti nei nomi, nei parametri e nei tipi. Le implementazioni interne sono libere.

### 3.1 `registry.py` (TASK-73)

```python
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

RULE_ID_PATTERN = r"^[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*$"
GROUPS: tuple[str, ...] = ("A", "B", "C", "D")
SEVERITIES: tuple[str, ...] = ("P0", "P1", "P2")          # P0 più grave
SCOPE_KINDS: tuple[str, ...] = ("portfolio", "aggregate", "instrument", "user")
RULE_STATUSES: tuple[str, ...] = ("pass", "fail", "skip", "error")
SKIP_CODES: tuple[str, ...] = (
    "empty_portfolio", "no_targets", "scenario_not_available", "truncated_output",
    "no_reference_data", "not_applicable", "aggregate_too_small", "no_transactions",
    "no_history", "feature_disabled",
)
ERROR_CODES: tuple[str, ...] = (
    "exception", "timeout", "tool_error", "invalid_outcome", "deadline_exceeded",
)
FAIL_CODE_DEFAULT = "invariant_violated"
# Aree mostrate all'utente (TASK-81): codice -> etichetta italiana.
AREAS: dict[str, str] = {
    "stress": "Stress test",
    "classification": "Classificazione degli strumenti",
    "rebalance": "Ribilanciamento e PAC",
    "simulation": "Simulazioni",
    "costs": "Costi",
    "income": "Reddito e dividendi",
    "montecarlo": "Proiezioni Monte Carlo",
    "daily": "Variazioni giornaliere",
    "values": "Valori, pesi e liquidità",
    "aggregate": "Vista aggregata",
    "performance": "Rendimenti",
    "doctor": "Metriche del Doctor",
    "data": "Qualità dei dati importati",
}
DEFAULT_RULE_TIMEOUT_S = 30.0
MAX_EVIDENCE_ITEMS = 50


@dataclass(frozen=True)
class Rule:
    id: str                       # stabile, RULE_ID_PATTERN, prefisso = group
    group: str                    # "A" | "B" | "C" | "D"
    title: str                    # italiano, per l'utente: niente id, niente gergo
    area: str                     # chiave di AREAS
    severity: str                 # "P0" | "P1" | "P2"
    findings: tuple[str, ...]     # es. ("V365-002",); vuota solo per regole senza finding
    scopes: tuple[str, ...]       # sottoinsieme non vuoto di SCOPE_KINDS
    tools: tuple[str, ...]        # tool (o "ctx.transactions" / "ctx.performance_audit") letti
    check: Callable[[Any, dict[str, Any]], dict[str, Any]]
    timeout_s: float = DEFAULT_RULE_TIMEOUT_S
    known_defect: str | None = None   # "TASK-NN" quando la regola trova un difetto reale aperto


class RuleRegistrationError(ValueError):
    """Dichiarazione non valida, id duplicato, filtro su un id o gruppo sconosciuto."""


def rule_from_declaration(declaration: Mapping[str, Any]) -> Rule: ...
def load_rules(modules: Sequence[str] | None = None) -> list[Rule]: ...
def select_rules(
    rules: Sequence[Rule], *, groups: Sequence[str] | None = None, rule_ids: Sequence[str] | None = None,
) -> list[Rule]: ...
```

- `load_rules(None)` importa `app.services.auditor.rules.<nome>` per ogni nome di
  `rules.RULE_MODULES = ("stress_classification", "rebalance_simulation", "costs_income",
  "consistency")`, legge la lista `RULES` di ciascun modulo e restituisce le regole ordinate per id.
  Un modulo **assente** (`ModuleNotFoundError` con `exc.name` uguale al modulo) è ignorato con un
  warning; qualunque altro errore di import si propaga (in CI deve fallire). `modules` esplicito
  serve ai test (moduli finti).
- La validazione rifiuta con `RuleRegistrationError`: id fuori pattern o duplicato, prefisso diverso
  da `group`, severità, area o scope sconosciuti, `title` vuoto, `check` non chiamabile,
  `timeout_s` ≤ 0 o > 300, `known_defect` fuori dal pattern `^TASK-[0-9]+$`.
- `select_rules`: filtri in AND; un id o un gruppo sconosciuto solleva `RuleRegistrationError`
  (la CLI esce con 2).

### 3.2 Dichiarazione di una regola (TASK-74…77)

Ogni modulo di gruppo espone una lista a livello di modulo:

```python
RULES: list[dict[str, Any]] = [
    {
        "id": "A-STRESS-SHOCK-TABLE",
        "group": "A",
        "title": "Lo stress test applica a ogni classe di attivo lo shock previsto",
        "area": "stress",
        "severity": "P0",
        "findings": ["V365-002"],
        "scopes": ["portfolio", "aggregate"],
        "tools": ["get_stress_test", "get_aggregate_stress_test"],
        "check": check_stress_shock_table,       # (ctx, scope) -> outcome dict
        # facoltativi:
        "timeout_s": 30.0,
        "known_defect": None,
    },
]
```

Id, titolo, area, severità, finding, scope e tool sono quelli del catalogo `rules.md` (copiati
esattamente). Import ammessi nei moduli delle regole: libreria standard;
`app.constants.stress_scenarios` (tabelle approvate di shock e proxy); `app.services.rebalance`
solo per `DEFAULT_TOLERANCE_PP`; `app.copilot_doctor_tools` solo per i messaggi costanti di
funzionalità disattivata; `app.services.auditor.offline_returns` (solo gruppo D). Nient'altro.

### 3.3 Esito restituito da `check` (outcome)

```python
{
    "status": "pass" | "fail" | "skip",
    "reason_code": None | "invariant_violated" | <SKIP_CODES>,   # obbligatorio per fail e skip
    "reason": None | str,      # frase italiana; obbligatoria per fail e skip
    "evidence": [Evidence, ...],   # fail: almeno 1; pass: facoltative (consigliate); skip: facoltative
}
```

`Evidence` (stessa forma ovunque; schema: `$defs/Evidence` di `schemas/report.schema.json`, l'esito
intero è `$defs/Outcome`):

```python
{
    "tool": "get_stress_test",            # nome del tool, oppure "ctx.transactions" / "ctx.performance_audit"
    "args": {"portfolio_id": 9101},       # argomenti esatti della chiamata
    "path": "scenarios[scenario_name=Bond Selloff].class_breakdown[asset_class=gold].shock_pct",
    "observed": -5.0,                     # qualunque valore JSON
    "expected": -10.0,                    # qualunque valore JSON (null se non c'è un valore atteso puntuale)
    "tolerance": 0.005,                   # numero o null
    "note": None,                         # stringa breve o null
}
```

Sintassi di `path`: chiavi separate da `.`; elemento di lista per indice `[3]` o per selettore
`[chiave=valore]`; `[*]` per un aggregato su tutti gli elementi (con `note`, es. «somma»). Valori
derivati da più tool: un'evidenza per ciascun tool letto.

Un esito che non rispetta questa forma (chiave mancante, `status` = `error`, `reason_code` non
ammesso, evidenze non serializzabili) diventa `error` con codice `invalid_outcome`.

### 3.4 Scope

```python
{"kind": "portfolio",  "portfolio_id": 9101}
{"kind": "aggregate",  "portfolio_ids": [9101, 9102, 9103]}      # ordinati, distinti, 2-20, stessa valuta
{"kind": "instrument", "portfolio_id": 9103, "symbol": "XGLD.DE"}
{"kind": "user",       "portfolio_ids": [9101, 9102, 9103]}      # tutti i portafogli dell'esecuzione
```

`scope_key(scope) -> str`: `portfolio:9101`, `aggregate:9101,9102,9103`, `instrument:9103:XGLD.DE`,
`user`. È la chiave di ordinamento e dei riepiloghi `by_scope`.

### 3.5 `context.py` (TASK-73)

```python
from typing import Any, Mapping, Sequence
from app.mcp_server.tools import ToolDependencies

AGGREGATE_TOOL_OF: dict[str, str] = {
    "get_portfolio_summary": "get_aggregate_summary",
    "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance",
    "get_recent_transactions": "get_aggregate_recent_transactions",
    "get_portfolio_health": "get_aggregate_health",
    "get_monte_carlo": "get_aggregate_monte_carlo",
    "get_stress_test": "get_aggregate_stress_test",
    "get_xray_summary": "get_aggregate_xray",
}
DOCTOR_SCOPE_TOOLS: frozenset[str] = frozenset({
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
})
TRANSACTIONS_TOOL = "ctx.transactions"            # nome usato nelle evidenze e nella memo
PERFORMANCE_AUDIT_TOOL = "ctx.performance_audit"


class AuditToolError(RuntimeError):
    def __init__(self, tool: str, args: Mapping[str, Any], message: str) -> None: ...
    tool: str
    args: dict[str, Any]
    message: str


class AuditorOfflineError(RuntimeError):
    """Sollevata da OfflineFinanceClient: nessun provider esterno durante l'audit."""


class OfflineFinanceClient:
    """Ogni metodo pubblico solleva AuditorOfflineError (es. get_etf_top_holdings)."""
    def __getattr__(self, name: str) -> Any: ...


def build_tool_dependencies(*, offline: bool = True) -> ToolDependencies: ...
def canonical_key(tool: str, args: Mapping[str, Any]) -> str: ...
def scoped_tool_args(
    tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]: ...
def scope_key(scope: Mapping[str, Any]) -> str: ...


class AuditContext:
    user_id: str
    run_id: str
    mode: str          # "ci" | "local" | "nightly" | "agent"

    def __init__(self, deps: ToolDependencies, user_id: str, *, run_id: str, mode: str) -> None: ...
    def call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]: ...
    def try_call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]: ...
    def scoped(self, tool: str, scope: Mapping[str, Any],
               extra_args: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
    def portfolios(self) -> list[dict[str, Any]]: ...
    def transactions(self, portfolio_id: int) -> list[dict[str, Any]]: ...
    def performance_audit(self, portfolio_ids: Sequence[int]) -> dict[str, Any]: ...
    def call_stats(self) -> dict[str, Any]: ...


def discover_scopes(
    ctx: AuditContext, *, portfolio_ids: Sequence[int] | None = None,
    include_aggregate: bool = True, include_instruments: bool = True,
) -> list[dict[str, Any]]: ...
```

Semantica (vincolante, la usano anche i contesti finti dei test):

- `canonical_key(tool, args)` = `json.dumps({"tool": tool, "args": dict(args)}, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)`.
- `call(tool, args)`: se la chiave è in memo restituisce una **copia profonda** del valore (o
  rilancia lo stesso errore memorizzato); altrimenti esegue `run_tool_sync(deps, tool, dict(args),
  user_id)`, applica `sanitize_output`, memorizza e restituisce una copia. `McpToolError` e
  qualunque altra eccezione del tool diventano `AuditToolError(tool, args, message)` (anch'esso
  memorizzato); il runner trasforma un `AuditToolError` non gestito in `error`/`tool_error`. La
  memo è thread-safe e deduplica le chiamate in corso (due regole parallele sulla stessa chiave
  eseguono il tool una volta).
- `try_call(tool, args)` = `{"ok": True, "result": <dict>, "error": None}` oppure
  `{"ok": False, "result": None, "error": <messaggio>}`; stessa memo di `call`. Le regole non
  catturano eccezioni di `call`: per un errore **atteso** (es. vendita oltre il valore della
  posizione) usano `try_call`.
- `scoped(tool, scope, extra_args)` = `call(*scoped_tool_args(tool, scope, extra_args))` con:

  | scope | tool non Doctor | tool in `DOCTOR_SCOPE_TOOLS` |
  |---|---|---|
  | `portfolio`, `instrument` | `(tool, {"portfolio_id": pid, **extra})` | `(tool, {"portfolio_id": pid, **extra})` |
  | `aggregate` | `(AGGREGATE_TOOL_OF[tool], {"portfolio_ids": ids})`; `extra_args` non vuoti o tool senza aggregato → `ValueError` | `(tool, {"portfolio_id": ids[0], "portfolio_ids": ids, **extra})` |
  | `user` | `ValueError` | `ValueError` |

  Un tool già aggregato (`get_aggregate_*`) passato a `scoped` → `ValueError`.
- `portfolios()` = `call("list_portfolios", {})["portfolios"]`.
- `transactions(portfolio_id)` e `performance_audit(portfolio_ids)`: §5.4.
- `call_stats()` = `{"total": int, "cache_hits": int, "errors": int, "by_tool": {tool: int}}`
  (chiamate effettive al tool, senza le risposte dalla memo).
- `discover_scopes`: §5.3.

### 3.6 `runner.py` (TASK-73)

```python
from dataclasses import dataclass

@dataclass
class RunOptions:
    mode: str = "local"                         # "ci" | "local" | "nightly" | "agent"
    portfolio_ids: list[int] | None = None      # None = tutti i portafogli dell'utente
    groups: list[str] | None = None
    rule_ids: list[str] | None = None
    include_aggregate: bool = True
    include_instruments: bool = True
    fail_on: str = "P1"                         # soglia: conta fail/error con severità <= soglia
    strict_known: bool = False                  # True: anche i difetti noti contano per l'uscita
    rule_timeout_s: float | None = None         # tetto al timeout di ogni regola
    max_duration_s: float = 1800.0              # scadenza dell'intera esecuzione
    max_workers: int = 1                        # regole valutate in parallelo


def evaluate_rule(rule: Rule, ctx: AuditContext, scope: dict, *, timeout_s: float) -> dict: ...
def run_audit(ctx: AuditContext, rules: Sequence[Rule], options: RunOptions) -> dict: ...
def exit_code_for(report: dict, *, fail_on: str, strict_known: bool = False) -> int: ...
```

- `evaluate_rule` restituisce un **RuleResult** (§4.1). La regola gira in un thread di un
  executor; `timeout_s` = `min(rule.timeout_s, options.rule_timeout_s or inf)`. Superato il
  timeout → `error`/`timeout` (`reason` = «superato il limite di N s»); il thread abbandonato non
  blocca le altre regole. Eccezione della regola → `error`/`exception` con `reason` =
  `"<NomeEccezione>: <messaggio troncato a 300 caratteri>"`. `AuditToolError` → `error`/`tool_error`
  con tool e messaggio.
- `run_audit`: chiama `discover_scopes`, seleziona le regole (`select_rules`), valuta ogni regola su
  ogni scope il cui `kind` è in `rule.scopes`, in ordine (id regola, scope_key). Una regola con
  scope `user` gira una volta se l'esecuzione ha almeno un portafoglio. Oltre `max_duration_s` le
  coppie non ancora valutate ricevono `error`/`deadline_exceeded` e il report ha
  `deadline_exceeded: true`. Restituisce il report (§4.2) costruito da `report.build_report`.
- `exit_code_for`: 1 se esiste almeno un risultato con `status` in (`fail`, `error`) e severità
  uguale o più grave di `fail_on`, escludendo i `fail` con `known_defect` non nullo quando
  `strict_known` è falso (un `error` conta sempre); altrimenti 0.

**Codici di uscita della CLI**

| codice | quando |
|---|---|
| 0 | nessun `fail` o `error` alla soglia (`--fail-on`), difetti noti esclusi salvo `--strict-known` |
| 1 | almeno un `fail` o `error` alla soglia |
| 2 | errore d'uso o di configurazione prima della valutazione: argomenti non validi, id/gruppo sconosciuto, nessuna regola caricata, utente senza portafogli, database o `list_portfolios` non raggiungibili, report non valido rispetto allo schema |

### 3.7 `report.py` (TASK-73)

```python
REPORT_SCHEMA_VERSION = 1

def build_report(
    *, run_id: str, mode: str, user_id: str | None, started_at: datetime, finished_at: datetime,
    options: RunOptions, rules: Sequence[Rule], scopes: Sequence[dict], results: Sequence[dict],
    tool_calls: dict, deadline_exceeded: bool,
) -> dict: ...
def report_to_json(report: dict) -> str: ...        # json.dumps(indent=2, ensure_ascii=False)
def report_to_markdown(report: dict) -> str: ...
def validate_report(report: dict) -> None: ...      # jsonschema Draft 2020-12 su report_schema.json
def privacy_rows(report: dict) -> list[dict]: ...   # righe salvabili della corsa notturna (§7.2)
```

Markdown (`report_to_markdown`), in italiano, in quest'ordine:
1. titolo `# Auditor dei calcoli — <esito>` (`superato` se `exit_code` = 0, altrimenti `non superato`);
2. riga di testata: versione dell'app, modalità, data, durata, utente (solo `ci`/`local`/`agent`);
3. tabella severità × esito (P0, P1, P2 per riga; pass, fail, skip, error per colonna) e numero di
   difetti noti;
4. `## Fallimenti ed errori`: per severità, per regola, per scope; titolo, id, finding, `reason` e un
   elenco puntato delle evidenze (`path`: osservato → atteso, tolleranza);
5. `## Regole saltate`: tabella id, scope, codice, motivo;
6. `## Esiti per scope`: tabella scope_key × conteggi;
7. `## Chiamate ai tool`: totale, dalla memo, errori.

`report_to_markdown` deve stare sotto 1 MB (limite del riepilogo dei job GitHub): oltre, tronca le
evidenze dei `pass` e poi degli `skip`, mai quelle dei `fail`/`error`.

### 3.8 `__main__.py` — CLI (TASK-73)

```
python -m app.services.auditor --user USER_ID
    [--portfolio ID]...            # ripetibile; default: tutti i portafogli dell'utente
    [--group A|B|C|D]...           # ripetibile
    [--rule RULE_ID]...            # ripetibile
    [--no-aggregate] [--no-instruments]
    [--fail-on P0|P1|P2]           # default P1
    [--strict-known]
    [--mode ci|local|agent]        # default local ("nightly" solo dall'endpoint interno)
    [--format markdown|json]       # stdout, default markdown
    [--json-out PATH] [--md-out PATH]
    [--rule-timeout-s S] [--max-duration-s S] [--max-workers N]
    [--list-rules]                 # stampa id, gruppo, severità, titolo, known_defect; esce con 0
```

`def main(argv: list[str] | None = None) -> int`. Usa `build_tool_dependencies(offline=True)` con il
`DATABASE_URL` delle impostazioni dell'app; **non importa `app.main`** (che avvia scheduler e
servizi). Valida il report con `validate_report` prima di scriverlo.

## 4. Schemi del risultato e del report

Schema autorevole (JSON Schema Draft 2020-12, autosufficiente): `docs/auditor/schemas/report.schema.json`.
Il report è la radice; `$defs/RuleResult` è il risultato di una regola su uno scope, `$defs/Outcome`
l'esito restituito da `check`, `$defs/Evidence` e `$defs/Scope` i blocchi comuni. I test delle regole
possono validare i propri esiti contro `$defs/Outcome`. Esempio valido:
`docs/auditor/fixtures/report-example.json`. Le tabelle sotto lo riassumono.

### 4.1 RuleResult (risultato di una regola su uno scope)

| campo | tipo | note |
|---|---|---|
| `rule_id`, `group`, `severity`, `area`, `title` | string | dalla regola |
| `scope` | object | §3.4 |
| `scope_key` | string | `scope_key(scope)` |
| `status` | `pass` \| `fail` \| `skip` \| `error` | |
| `reason_code` | string \| null | null solo per `pass`; `fail` → `invariant_violated` (o codice proprio della regola, minuscolo `^[a-z][a-z0-9_]*$`); `skip` → `SKIP_CODES`; `error` → `ERROR_CODES` |
| `reason` | string \| null | italiano; obbligatorio salvo `pass` |
| `evidence` | Evidence[] | al massimo `MAX_EVIDENCE_ITEMS` (50) |
| `evidence_truncated` | boolean | true se il motore ha tagliato le evidenze |
| `duration_ms` | integer ≥ 0 | |
| `known_defect` | string \| null | `TASK-NN` |

### 4.2 Report di un'esecuzione

| campo | tipo | note |
|---|---|---|
| `schema_version` | 1 | |
| `run_id` | string | 32 caratteri esadecimali (`uuid4().hex`) |
| `mode` | `ci` \| `local` \| `nightly` \| `agent` | |
| `app_version` | string | `app.version.APP_VERSION` |
| `started_at`, `finished_at` | string | ISO 8601 in UTC con `Z` o `+00:00` |
| `duration_ms` | integer | |
| `user_id` | string \| null | null in `nightly` |
| `options` | object | `portfolio_ids`, `groups`, `rule_ids` (array o null), `include_aggregate`, `include_instruments`, `fail_on`, `strict_known` |
| `rules` | object[] | regole selezionate: `id`, `group`, `severity`, `area`, `title`, `findings`, `scopes`, `known_defect` |
| `scopes` | object[] | `{scope, scope_key}` in ordine di `scope_key` |
| `results` | RuleResult[] | ordinati per (severità P0→P2, `rule_id`, `scope_key`) |
| `counts` | object | `total`; `by_status` {pass, fail, skip, error}; `by_severity` {P0, P1, P2} → {pass, fail, skip, error}; `known_defect_failures` |
| `by_scope` | object | `scope_key` → {pass, fail, skip, error} |
| `by_rule` | object | `rule_id` → {pass, fail, skip, error} |
| `tool_calls` | object | `ctx.call_stats()` (somma sui contesti se più utenti) |
| `deadline_exceeded` | boolean | |
| `exit_code` | 0 \| 1 | `exit_code_for(report, fail_on=options.fail_on, strict_known=options.strict_known)` |

### 4.3 Codici

| esito | codici | prodotto da |
|---|---|---|
| `pass` | — | regola |
| `fail` | `invariant_violated` (default) | regola |
| `skip` | `empty_portfolio` (nessuna posizione), `no_targets` (nessun target), `scenario_not_available` (tutti gli scenari `not_available`), `truncated_output` (output limitato a 30 righe: la somma non è verificabile), `no_reference_data` (dato di riferimento assente: TER, rendimento, dividendi, chiusura precedente), `not_applicable` (precondizione della regola non vera per questo scope, es. strumento non ETC), `aggregate_too_small` (meno di 2 portafogli), `no_transactions`, `no_history` (nessuno storico prezzi: Monte Carlo vuoto), `feature_disabled` (funzione dell'app spenta da configurazione) | regola |
| `error` | `exception`, `timeout`, `tool_error`, `invalid_outcome`, `deadline_exceeded` | motore |

### 4.4 Severità

| severità | significato | esempi di novembre |
|---|---|---|
| P0 | numero sbagliato che può portare direttamente a una decisione sbagliata (perdite stimate, ordini, capitale) | V365-001, V365-002, V365-003 |
| P1 | numero incoerente fra tool o incompleto presentato come completo; dato importato errato | V365-004…009, V-TER-UNIT, V-XLSX-1000, C1-TWR-MIXED |
| P2 | trasparenza, coerenza secondaria, metadati | V365-010…013, V-DIV-MIXED-CCY, V-BOND-QUOTETYPE |

La severità di una regola è quella del catalogo; può differire da quella del finding di origine
quando l'impatto sui numeri mostrati è maggiore (motivato nel catalogo).

## 5. Contesto, tool e scope

### 5.1 Dipendenze e memoizzazione

`build_tool_dependencies(offline=True)` costruisce `ToolDependencies(repo=PortfolioRepository(...),
performance_service=PerformanceService(repo), finance_client=OfflineFinanceClient())` come
`register_mcp_routes` (stesso repository e stesso servizio; nessun client justETF, quindi l'X-Ray non
scrive mai `etf_enrichment`). Un `AuditContext` per utente e per esecuzione: la memo non è mai
condivisa fra utenti né fra esecuzioni. Le regole ricevono copie: possono modificare i `dict` senza
effetti sulle altre.

`run_tool_sync` restituisce già i valori che il client MCP riceve, salvo `sanitize_output` (testo
ripulito, date in stringa, non finiti → null) e il troncamento a 200 KB, che l'Auditor **non**
applica (le regole devono vedere l'output completo). Il blocco `data_freshness` aggiunto ai tool di
`FRESHNESS_TOOLS` è presente come per il client.

### 5.2 Argomenti canonici

Per condividere la memo fra regole, ogni regola usa **esattamente** questi argomenti (in tabella gli
argomenti oltre `portfolio_id` / `portfolio_ids` aggiunti da `scoped`):

| tool | argomenti | usato da |
|---|---|---|
| `list_portfolios` | `{}` | motore, A |
| `get_portfolio_summary` / `get_aggregate_summary` | — | B, D |
| `get_positions` / `get_aggregate_positions` | — | A, B, C, D, motore |
| `get_cash_balance` | — | D |
| `get_target_drift` | — | B |
| `get_performance` / `get_aggregate_performance` | — | D |
| `get_portfolio_health` / `get_aggregate_health` | — | D |
| `get_day_movers` | — | C |
| `get_monte_carlo` / `get_aggregate_monte_carlo` | — | C |
| `get_stress_test` / `get_aggregate_stress_test` | — | A, D |
| `get_xray_summary` / `get_aggregate_xray` | — | D |
| `get_cost_breakdown` | — | A, C, D |
| `get_income_projection` | — | C |
| `get_dividend_summary` | — | C |
| `search_asset_info` | `{"symbol": <simbolo esatto della posizione>}` | A, C, D |
| `read_doctor_metrics` | — (nessun `metric_codes`) | D |
| `calculate_rebalance_orders` | `{"mode": "rebalance"}`; `{"mode": "buy_only", "available_cash": 1000.0}`; `{"mode": "sell_only"}` | B |
| `calculate_pac_contribution` | `{"monthly_amount": 500.0}` | B |
| `calculate_what_if` | `{"action": "buy", "symbol": S, "amount_eur": 1000.0}`; `{"action": "sell", "symbol": S, "amount_eur": round(V/2, 2)}`; `{"action": "sell", "symbol": S, "amount_eur": round(V + 1000.0, 2)}` con S = simbolo della prima riga di `get_positions` (peso maggiore) e V = il suo `market_value` | B |

Gli importi fissi (1000 €, 500 €) rendono l'esito riproducibile e restano sotto i limiti degli schemi
MCP (`_MAX_AMOUNT`). Nessun'altra combinazione di argomenti è ammessa senza aggiornare questa tabella.

### 5.3 Scope: come si ottengono

`discover_scopes(ctx, portfolio_ids, include_aggregate, include_instruments)`:

1. **portfolio**: uno scope per ogni portafoglio di `ctx.portfolios()` (filtrato da `portfolio_ids`
   se dato; un id non dell'utente → errore d'uso, CLI 2), in ordine di id.
2. **aggregate** (se `include_aggregate`): i portafogli selezionati raggruppati per `base_currency`;
   ogni gruppo con almeno 2 portafogli dà uno scope con i primi 20 id in ordine crescente
   (`MAX_AGGREGATE_PORTFOLIOS`). Un gruppo di 1 non produce scope (le regole aggregate non vanno in
   `skip`: semplicemente non girano).
3. **instrument** (se `include_instruments`): per ogni scope portfolio, uno scope per ogni riga di
   `ctx.scoped("get_positions", scope)["positions"]` (al più 30, già ordinate per peso), con
   `symbol` esatto della riga; ordine di `scope_key`.
4. **user**: uno, con `portfolio_ids` = tutti i portafogli selezionati.

### 5.4 Letture dirette ammesse (le uniche)

| metodo | perché un tool non basta | implementazione | memo |
|---|---|---|---|
| `ctx.transactions(portfolio_id)` | `get_recent_transactions` restituisce solo le ultime 20; duplicati e prezzi d'import richiedono tutte le transazioni | `deps.repo.list_transactions(portfolio_id, user_id)` (la stessa lettura del tool, già con verifica di proprietà) | chiave `canonical_key("ctx.transactions", {"portfolio_id": pid})` |
| `ctx.performance_audit(portfolio_ids)` | `get_aggregate_performance_audit` esiste solo per 2-20 portafogli | 2+ id → `call("get_aggregate_performance_audit", {"portfolio_ids": ids})`; 1 id → `build_performance_audit_export(deps.performance_service, pid, user_id, period="1y", max_flows=200, offset=0)` (la funzione del tool) + `sanitize_output` | 1 id: `canonical_key("ctx.performance_audit", {"portfolio_ids": [pid]})` |

`transactions` restituisce, in ordine `trade_at` decrescente e `id` decrescente, dict con **solo**
queste chiavi: `id` (int), `asset_id` (int | null), `symbol` (str | null), `side` (str), `trade_at`
(ISO 8601), `trade_date` (YYYY-MM-DD, data UTC di `trade_at`), `quantity`, `price`, `fees`, `taxes`
(float), `trade_currency` (str). Note e nomi degli strumenti sono esclusi. Gli errori diventano
`AuditToolError` con `tool` = `ctx.transactions` / `ctx.performance_audit`.

### 5.5 Provider offline

`OfflineFinanceClient` solleva `AuditorOfflineError` a ogni chiamata. Oggi l'unico uso nei tool è
`get_etf_top_holdings` nell'X-Ray (`_xray.py`), che tratta l'eccezione come «dati mancanti»
(`lookthrough_status: missing`) senza memorizzarla. L'X-Ray dell'Auditor usa quindi solo i dati già
salvati (`etf_enrichment`), come in produzione dopo un errore di rete. Se un tool nuovo usasse il
finance client in altro modo, l'esito sarebbe `error`/`tool_error`, non un dato inventato.

### 5.6 Tool per gruppo

| gruppo | task | tool letti | scope |
|---|---|---|---|
| A — stress test e classificazione | 74 | `get_stress_test`, `get_aggregate_stress_test`, `get_positions`, `search_asset_info`, `get_cost_breakdown` | portfolio, aggregate, instrument, user |
| B — ribilanciamento, PAC, simulazioni | 75 | `calculate_rebalance_orders`, `calculate_pac_contribution`, `calculate_what_if`, `get_positions`, `get_portfolio_summary`, `get_target_drift` | portfolio |
| C — costi, reddito, dividendi, Monte Carlo, variazioni | 76 | `get_cost_breakdown`, `get_income_projection`, `get_dividend_summary`, `get_monte_carlo`, `get_aggregate_monte_carlo`, `get_day_movers`, `get_positions`, `search_asset_info`, `ctx.transactions` | portfolio, aggregate |
| D — coerenza fra tool, aggregata, dati | 77 | `get_portfolio_summary`, `get_positions`, `get_cash_balance`, `get_performance`, `get_portfolio_health`, `get_stress_test`, `get_xray_summary`, `get_cost_breakdown`, `read_doctor_metrics`, `search_asset_info`, tutti i `get_aggregate_*` tranne `recent_transactions`, `ctx.transactions`, `ctx.performance_audit` | portfolio, aggregate, instrument |

Il dettaglio per regola (tool, argomenti, percorsi dei campi) è in `rules.md`.

## 6. Modalità di esecuzione

| | CI su portafogli di prova (TASK-79) | notturna in produzione (TASK-80) | agente settimanale (TASK-82) |
|---|---|---|---|
| avvio | workflow `.github/workflows/auditor.yml`: PR su `src/backend/**` o `database/**`, ogni notte, a mano | workflow `.github/workflows/auditor-production.yml` (cron `35 23 * * *`, dopo la sincronizzazione delle 22:40 UTC, più `workflow_dispatch`) → `POST /api/internal/auditor/run` | sessione Claude programmata, una volta a settimana |
| dati | Postgres effimero: `database/schema.sql`, migrazioni, `scripts/auditor/audit_seed.sql` (utente `auditor-seed-user`) | database di produzione, tutti gli utenti con almeno un portafoglio (`select distinct owner_user_id from portfolios`) | stack locale con lo stesso seed (`scripts/auditor/agent_stack.sh`); **mai** dati di produzione |
| come | CLI `--user auditor-seed-user --mode ci --fail-on P1 --json-out auditor-report.json --md-out auditor-report.md` | in processo, thread in background: per utente `AuditContext` + `run_audit(mode="nightly")`, `AUDITOR_MAX_CONCURRENCY` utenti in parallelo, timeout e durata massima configurabili | CLI `--mode agent`, poi esplorazione con `scripts/auditor/mcp_call.py` |
| scrive | riepilogo del job (Markdown), artefatto JSON; nessuna scrittura nel DB oltre al seed | solo `auditor_runs` e `auditor_results` (§7.2) | `docs/auditor/reports/<YYYY-MM-DD>.md`, task in `backlog/tasks/`, PR in bozza |
| esito | job fallito con codice di uscita 1 (`fail`/`error` P0 o P1, difetti noti esclusi) | job fallito se l'endpoint non risponde o la corsa finisce `failed`/`interrupted`; warning se `completed_with_failures` | PR in bozza, nessuna modifica al codice applicativo |
| evidenza | completa | non salvata | completa (solo dati di prova) |

### 6.1 Endpoint della corsa notturna (TASK-80)

Modello: `api/routes_internal.py` (token `Bearer` confrontato con `hmac.compare_digest`, endpoint
che rispondono 404 se il token non è impostato, limiti per IP, esclusi dallo schema OpenAPI).

| endpoint | auth | risposta |
|---|---|---|
| `POST /api/internal/auditor/run` | `Authorization: Bearer <AUDITOR_RUN_TOKEN>` | 202 `{"run_id": str, "status": "running"}`; 409 `{"code": "already_running", "run_id": str, "error": {...}}`; 401 token errato; 404 token non impostato; 429 limite |
| `GET /api/internal/auditor/run/status` | stesso token | 200 `{"running": RunSummary \| null, "last_run": RunSummary \| null}` |
| `GET /api/admin/auditor/latest` | `require_admin` | 200 `{"run": RunSummary \| null, "failing": [{"rule_id", "title", "area", "severity", "portfolios_failing": int, "since": ISO 8601}], "errors": [{"rule_id", "portfolios": int}]}` |
| `GET /api/doctor/auditor/summary?portfolio_id=N` oppure `?portfolio_ids=1,2,3` (TASK-81) | `require_auth` + proprietà di ogni id | 200 `{"available": bool, "run_finished_at": ISO \| null, "checks_passed": int, "checks_in_review": int, "areas": [{"area": str, "label": str, "status": "passed" \| "in_review", "checks": [{"title": str, "status": "passed" \| "in_review"}]}]}` |

`RunSummary` = `{"run_id", "status", "trigger", "app_version", "started_at", "finished_at",
"portfolios_total", "rules_total", "counts": {"pass", "fail", "skip", "error"}, "failing_rules":
[{"rule_id", "severity", "portfolios": int}]}`: solo conteggi e id di regole, nessun dato utente.
`status` di una corsa: `running`, `success` (nessun `fail`/`error`), `completed_with_failures`,
`failed` (il motore si è fermato: DB, eccezione fuori dalle regole), `interrupted` (trovata
`running` all'avvio dell'app). Una corsa `running` blocca l'avvio di un'altra (lock in tabella, come
`market_data_sync`). `since` = inizio della prima corsa della serie ininterrotta di corse concluse
in cui la regola fallisce su almeno un portafoglio.

Endpoint utente (TASK-81): per ogni regola, l'esito peggiore (`fail` > `error` > `skip` > `pass`)
fra le righe dell'ultima corsa conclusa dei portafogli richiesti (per una vista aggregata,
l'unione delle righe dei portafogli che la compongono); `passed` = esito `pass`, `in_review` =
esito `fail`; `error` e `skip` non sono mostrati né contati. `available: false` se non c'è una corsa
conclusa o se è finita da più di 48 ore. Titoli e aree vengono dal registro delle regole
(`load_rules()`), mai id interni.

## 7. Privacy

### 7.1 Cosa contiene un'evidenza

- **CI, locale, agente:** tutto (simboli, importi, pesi, argomenti, messaggi d'errore). Sono dati di
  prova sintetici del seed: possono finire negli artefatti, nei riepiloghi dei job e nei report
  dell'agente versionati nel repository.
- **Corsa notturna in produzione:** l'evidenza esiste solo in memoria durante la valutazione e non
  viene mai salvata, loggata, restituita da un endpoint né inviata fuori dal server. Lo stesso vale
  per `reason` (può contenere importi o simboli) e per i messaggi d'eccezione.

### 7.2 Cosa si salva della corsa notturna

`privacy_rows(report)` (TASK-73) restituisce righe `{"portfolio_id": int, "rule_id": str,
"scope_kind": str, "status": str, "severity": str}`:

- scope `portfolio`: una riga;
- scope `instrument`: collassato sul portafoglio (il simbolo non si salva), esito peggiore;
- scope `aggregate` e `user`: una riga per ogni portafoglio membro, con `scope_kind` invariato;
- per chiave (`portfolio_id`, `rule_id`, `scope_kind`) resta l'esito peggiore
  (`fail` > `error` > `skip` > `pass`).

TASK-80 salva queste righe con `run_id` e data in `auditor_results`, e in `auditor_runs` solo stato,
date, versione, trigger, conteggi e, per una corsa `failed`, il **nome** dell'eccezione (mai il
testo). Nessun importo, nome di strumento, simbolo, nome di portafoglio o testo di evidenza. I log
della corsa riportano run_id, durata, conteggi e id delle regole che falliscono, mai portafogli,
utenti o valori.

Tabelle (TASK-80, migrazione in `database/migrations/` e `database/schema.sql`):

```sql
create table auditor_runs (
  id bigserial primary key,
  run_uuid text not null unique,
  status text not null check (status in ('running','success','completed_with_failures','failed','interrupted')),
  trigger text not null check (trigger in ('external','manual')),
  app_version text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  portfolios_total integer not null default 0,
  rules_total integer not null default 0,
  pass_count integer not null default 0,
  fail_count integer not null default 0,
  skip_count integer not null default 0,
  error_count integer not null default 0,
  error_type text
);
create table auditor_results (
  run_id bigint not null references auditor_runs(id) on delete cascade,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  rule_id text not null,
  scope_kind text not null check (scope_kind in ('portfolio','aggregate','instrument','user')),
  status text not null check (status in ('pass','fail','skip','error')),
  severity text not null check (severity in ('P0','P1','P2')),
  created_at timestamptz not null default now(),
  primary key (run_id, portfolio_id, rule_id, scope_kind)
);
```

### 7.3 Cosa vede chi

| chi | vede |
|---|---|
| utente (Doctor, TASK-81) | «Calcoli verificati: N controlli superati» e data dell'ultima corsa; elenco dei controlli dei **propri** portafogli per titolo e area con esito superato / in verifica; nessun id, nessuna evidenza, nessun valore; testo neutro se un controllo è in verifica |
| amministratore (TASK-80/81) | ultima corsa: regole che falliscono, severità, **numero** di portafogli coinvolti, da quando; nessun id di utente o portafoglio, nessuna evidenza |
| sviluppatori in CI | report completo sul seed |
| agente settimanale | solo seed locale e codice; i suoi report contengono solo valori del seed |

## 8. Configurazione

| variabile | default | uso |
|---|---|---|
| `AUDITOR_RUN_TOKEN` | vuoto (endpoint disattivati, 404) | token degli endpoint interni (TASK-80); solo nei secret di GitHub e su Render |
| `AUDITOR_MAX_CONCURRENCY` | 2 | utenti valutati in parallelo nella notturna |
| `AUDITOR_MAX_DURATION_S` | 1800 | durata massima della corsa notturna (`RunOptions.max_duration_s`) |
| `AUDITOR_RULE_TIMEOUT_S` | 30 | tetto al timeout di una regola (`RunOptions.rule_timeout_s`) |
| `AUDITOR_RUN_RATE_LIMIT_REQUESTS` / `_WINDOW_SECONDS` | 4 / 3600 | POST di avvio, per IP |
| `AUDITOR_STATUS_RATE_LIMIT_REQUESTS` | 240 | GET di stato, per IP, stessa finestra |
| `AUDITOR_AUTH_FAILURE_LIMIT_REQUESTS` | 30 | tentativi con token errato, per IP |

Secret del workflow di produzione: `VALORE365_API_BASE_URL` (già usato dalla sincronizzazione) e
`AUDITOR_RUN_TOKEN`; il token passa a `curl` da stdin come in `market-data-sync.yml`.

## 9. Determinismo

- Seed con date relative a `current_date` (come `scripts/e2e/doctor2_seed.sql`), prezzi e cambi nel
  seed, nessuna rete.
- Monte Carlo con seed fisso 42 (`_monte_carlo.py`): stesso input, stesso output.
- Argomenti fissi dei tool di simulazione (§5.2).
- Ordine di valutazione e del report deterministico (id regola, scope_key).
- Le regole non usano l'ora corrente salvo per confrontare date restituite dai tool.

## 10. Test

Ogni task di regole verifica, per ogni regola, con un contesto finto: (1) `pass` su dati corretti;
(2) `fail` quando si reintroduce il difetto del finding (output sbagliato riprodotto o monkeypatch
del codice corretto); (3) `skip` con il codice giusto quando i dati non bastano. Una regola che non
fallisce sul proprio difetto non è accettata. TASK-73 testa il motore con regole e tool finti.

Contesto finto di riferimento: **copiarlo** in ogni file di test delle regole (nessun modulo di test
condiviso). Implementa la stessa interfaccia e la stessa `scoped_tool_args` del contesto vero.

```python
import copy
import json
from typing import Any, Mapping, Sequence

AGGREGATE_TOOL_OF = {
    "get_portfolio_summary": "get_aggregate_summary", "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance", "get_recent_transactions": "get_aggregate_recent_transactions",
    "get_portfolio_health": "get_aggregate_health", "get_monte_carlo": "get_aggregate_monte_carlo",
    "get_stress_test": "get_aggregate_stress_test", "get_xray_summary": "get_aggregate_xray",
}
DOCTOR_SCOPE_TOOLS = frozenset({
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
})


def canonical_key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps({"tool": tool, "args": dict(args)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scoped_tool_args(tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
    extra = dict(extra_args or {})
    if tool.startswith("get_aggregate_"):
        raise ValueError("passare il tool del portafoglio singolo")
    kind = scope["kind"]
    if kind in ("portfolio", "instrument"):
        return tool, {"portfolio_id": scope["portfolio_id"], **extra}
    if kind == "aggregate":
        ids = list(scope["portfolio_ids"])
        if tool in DOCTOR_SCOPE_TOOLS:
            return tool, {"portfolio_id": ids[0], "portfolio_ids": ids, **extra}
        if extra or tool not in AGGREGATE_TOOL_OF:
            raise ValueError(f"{tool} non ha una variante aggregata")
        return AGGREGATE_TOOL_OF[tool], {"portfolio_ids": ids}
    raise ValueError(f"scope {kind} non ammesso per {tool}")


class FakeToolError(RuntimeError):
    def __init__(self, tool: str, args: Mapping[str, Any], message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool, self.args, self.message = tool, dict(args), message


class FakeAuditContext:
    """responses: [(tool, args, result_dict | Exception)]; transactions: {pid: [tx]};
    performance_audit: {tuple(sorted(ids)): export}; portfolios: [{"id", "name", "base_currency"}]."""

    def __init__(self, responses=(), *, transactions=None, performance_audit=None, portfolios=None,
                 user_id: str = "test-user") -> None:
        self.user_id, self.run_id, self.mode = user_id, "0" * 32, "local"
        self._responses = {canonical_key(t, a): r for t, a, r in responses}
        self._transactions = dict(transactions or {})
        self._performance_audit = dict(performance_audit or {})
        if portfolios is not None:
            self._responses[canonical_key("list_portfolios", {})] = {"portfolios": list(portfolios)}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, dict(args)))
        key = canonical_key(tool, args)
        if key not in self._responses:
            raise KeyError(f"risposta finta mancante: {key}")
        value = self._responses[key]
        if isinstance(value, Exception):
            raise FakeToolError(tool, args, str(value))
        return copy.deepcopy(value)

    def try_call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.call(tool, args), "error": None}
        except FakeToolError as exc:
            return {"ok": False, "result": None, "error": exc.message}

    def scoped(self, tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
        return self.call(*scoped_tool_args(tool, scope, extra_args))

    def portfolios(self) -> list[dict[str, Any]]:
        return self.call("list_portfolios", {})["portfolios"]

    def transactions(self, portfolio_id: int) -> list[dict[str, Any]]:
        return copy.deepcopy(self._transactions[portfolio_id])

    def performance_audit(self, portfolio_ids: Sequence[int]) -> dict[str, Any]:
        return copy.deepcopy(self._performance_audit[tuple(sorted(portfolio_ids))])

    def call_stats(self) -> dict[str, Any]:
        return {"total": len(self.calls), "cache_hits": 0, "errors": 0, "by_tool": {}}
```

Un test che vuole simulare un errore di tool mette un'`Exception` come risposta: la regola, che non
cattura le eccezioni di `call`, la lascia salire (nel motore vero diventerebbe `error`/`tool_error`).
Le chiavi della risposta finta devono essere quelle **reali** dei tool (`copilot_tools.py`,
`aggregate_tools.py`): un test con chiavi inventate non dimostra nulla.

## 11. Proprietà dei file (task → file)

| task | file | note |
|---|---|---|
| 72 | `docs/auditor/architecture.md`, `docs/auditor/rules.md`, `docs/auditor/agent-playbook.md`, `docs/auditor/schemas/report.schema.json`, `docs/auditor/fixtures/report-example.json` | contratto; i task successivi aggiungono solo voci in «Deviazioni» e, TASK-79, la sezione «Difetti noti» di `rules.md` |
| 73 | `src/backend/app/services/auditor/__init__.py`, `registry.py`, `context.py`, `runner.py`, `report.py`, `report_schema.json`, `__main__.py`, `rules/__init__.py`, `src/backend/tests/unit/test_auditor_engine.py` | unico task che crea `__init__.py` |
| 74 | `src/backend/app/services/auditor/rules/stress_classification.py`, `src/backend/tests/unit/test_auditor_rules_stress.py` | |
| 75 | `src/backend/app/services/auditor/rules/rebalance_simulation.py`, `src/backend/tests/unit/test_auditor_rules_rebalance.py` | |
| 76 | `src/backend/app/services/auditor/rules/costs_income.py`, `src/backend/tests/unit/test_auditor_rules_costs.py` | |
| 77 | `src/backend/app/services/auditor/rules/consistency.py`, `src/backend/app/services/auditor/offline_returns.py`, `scripts/audit/twr_mwr_offline_auditor.py` (solo per delegare a `offline_returns`, CLI e output invariati), `src/backend/tests/unit/test_auditor_rules_consistency.py` | lo script trova il modulo aggiungendo `<repo>/src/backend` a `sys.path` in base alla propria posizione; test di non regressione sullo stesso export |
| 78 | `scripts/auditor/audit_seed.sql`, `scripts/auditor/README.md`, `src/backend/tests/integration/test_auditor_seed_postgres.py` | portafogli e requisiti in `rules.md` §1 |
| 79 | `.github/workflows/auditor.yml`, `src/backend/tests/integration/test_auditor_postgres.py`, sezione «Auditor» di `src/backend/README.md`, task nuovi in `backlog/tasks/`, `rules.md` §6 «Difetti noti» e il campo `known_defect` nelle dichiarazioni delle regole interessate | dopo TASK-73…78 |
| 80 | `src/backend/app/api/routes_auditor_internal.py`, `src/backend/app/services/auditor/store.py`, registrazione in `src/backend/app/main.py`, `src/backend/app/config.py`, `.env.example`, `database/migrations/<data>_01_auditor.sql`, `database/schema.sql`, `.github/workflows/auditor-production.yml`, `src/backend/tests/unit/test_auditor_store.py`, `src/backend/tests/unit/test_auditor_internal_routes.py`, `src/backend/tests/integration/test_auditor_store_postgres.py` | |
| 81 | `src/frontend/valore-frontend/src/components/doctor/AuditIndicator.tsx` e test, client in `src/services/api/`, montaggio minimo in `pages/Doctor.page.tsx` e `pages/Admin.page.tsx`, `src/backend/app/api/routes_auditor_user.py` (+ registrazione in `main.py`), `src/backend/tests/unit/test_auditor_user_route.py` | endpoint utente di §6.1 |
| 82 | `scripts/auditor/mcp_call.py`, `scripts/auditor/agent_stack.sh`, aggiornamenti di `docs/auditor/agent-playbook.md`, `docs/auditor/reports/` | |

## Deviazioni

Ogni task che si discosta da questo contratto aggiunge qui una sottosezione `### TASK-NN` con cosa
cambia, perché, e quali task ne sono toccati.
