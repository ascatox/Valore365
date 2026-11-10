# Tribunale del portafoglio — Architettura

Riferimenti: contratto `docs/tribunale/api-contracts.md` (schemi, eventi, codici, limiti),
specifica UI `docs/tribunale/ui-spec.md`, fixture `docs/tribunale/fixtures/`. Questo documento
descrive come i pezzi sono collegati, chi possiede quale file e quali firme pubbliche i task si
scambiano. Le regole sui dati restano nel contratto.

Principio: **il Doctor calcola, l'AI interpreta, un controllo deterministico decide cosa
arriva all'utente.** Il modello non vede mai importi, non produce numeri e non sceglie lo scope.

## 1. Flusso della seduta

```
Frontend (sezione «Tribunale» del Doctor)
  │ GET  /api/doctor/tribunal/status            → disponibilità, chiave, limite
  │ GET  /api/doctor/tribunal/sessions/latest   → ultima seduta salvata + data_changed
  │ POST /api/doctor/tribunal/sessions          → stream SSE
  ▼
routes_tribunal ──(auth, flag, parsing scope, DoctorRoute)──► TribunalOrchestrator.start()
                                                               │
   controlli prima dello stream (errori JSON):                 │
   1 flag  2 scope (resolve_scope)  3 config Copilot  4 lock utente
   5 case_file.build_case_file()  ── Doctor: snapshot, metriche, health, X-Ray, stress,
                                     Monte Carlo, evaluation policy (nessun LLM)
   6 riuso (store.get_latest + hash)  7 limite (store.count_today)
                                                               ▼
                                         generatore SSE (StreamingResponse)
   session → case_file
   phase apertura ── ThreadPool(3): personas.build_opening_request(v) → structured.call_structured
                     → verifier.verify_opening(v) → argument* + discarded | voice_error   (per voce, appena pronta)
   [voci valide < 2 → error too_few_voices]
   phase replica  ── ThreadPool(voci valide): build_rebuttal_request → call_structured
                     → verifier.verify_rebuttals → rebuttal* + discarded | voice_error
   phase sintesi  ── build_synthesis_request(argomenti e repliche ammessi) → call_structured
                     → verifier.verify_synthesis → synthesis + discarded | error synthesis_failed
   done ── store.save(seduta) (solo se conclusa)                keepalive ogni 10 s durante le attese
```

Le uniche scritture sono le sedute salvate e il contatore d'uso (TASK-66). Posizioni,
transazioni, policy e prezzi sono solo letti.

## 2. Moduli backend — `src/backend/app/services/tribunal/`

Lo scambio tra moduli avviene con **`dict` JSON-serializzabili conformi agli schemi del
contratto** (non modelli Pydantic condivisi): i task sono paralleli e nessuno deve dipendere da
classi scritte da un altro. Pydantic resta libero all'interno di un modulo e nelle route.

| file | task | responsabilità |
|---|---|---|
| `__init__.py` | 61 | solo docstring del package; **nessuna re-export** (evita import circolari e conflitti) |
| `case_file.py` | 61 | fascicolo deterministico, id, formattazione, hash |
| `personas.py` | 63 | voci, temi, prompt per fase, schemi JSON delle risposte |
| `verifier.py` | 64 | verificatore puro, codici di scarto, limiti |
| `orchestrator.py` | 65 (+ 66 minimo) | sequenza della seduta, SSE, timeout, lock, config, store |
| `store.py` | 66 | persistenza dell'ultima seduta e contatore giornaliero |

Altri file backend:

| file | task | responsabilità |
|---|---|---|
| `app/copilot/structured.py` | 62 | chiamata LLM con risposta strutturata per OpenAI, Anthropic, Gemini, OpenRouter |
| `app/prompts/tribunal_*.txt` | 63 | testi dei prompt (separati dal codice) |
| `app/api/routes_tribunal.py` | 65 (+ 66 minimo) | `register_tribunal_routes` |

### 2.1 Firme pubbliche

Le firme qui sotto sono il contratto tra task: nome, parametri, tipo di ritorno ed eccezioni.
Parametri aggiuntivi sono ammessi solo se keyword-only e con default.

#### `services/tribunal/case_file.py` (TASK-61)

```python
CONTRACT_VERSION: str = "tribunale-1.0"
CASE_FILE_SCHEMA_VERSION: int = 1
MAX_FACTS: int = 40
MIN_CITABLE_FACTS: int = 6
MAX_INSTRUMENTS: int = 30
HASH_FACT_FIELDS: tuple[str, ...]   # api-contracts §4.6

def build_case_file(
    repo: Any, user_id: str, portfolio_ids: Iterable[int], *,
    service: "DoctorPolicyService | None" = None,   # default: get_doctor_policy_service(repo)
    now: datetime | None = None,                    # generated_at; default datetime.now(UTC)
) -> dict[str, Any]:
    """CaseFile (api-contracts §4.2). status "empty_portfolio" con facts [] se lo scope non ha
    posizioni investite. Solleva doctor_policy.errors.InvalidRequest (400) e NotFound (404)
    come DoctorPolicyService.resolve_scope. Non chiama mai un LLM."""

def compute_case_file_hash(case_file: Mapping[str, Any]) -> str      # 64 hex, api-contracts §4.6
def facts_by_id(case_file: Mapping[str, Any]) -> dict[str, dict[str, Any]]
def format_fact_value(value: float | int | str | None, unit: str, *, decimals: int = 1) -> str  # §4.5
```

Riusa senza duplicare: `DoctorPolicyService.resolve_scope` / `._snapshot_and_metrics` (o
`build_snapshot` + `compute_metrics`), `canonical_securities`, `format_it`,
`analyze_portfolio_health`, `compute_portfolio_xray`, `run_stress_test`,
`run_monte_carlo_projection` (con `int` per lo scope singolo e `list[int]` per l'aggregato),
`DoctorPolicyService.evaluate`, `copilot_doctor_tools.clean_text` (import dentro la funzione se
serve a evitare cicli: `doctor_policy.snapshot → mcp_server → copilot_tools`). Usa
`repo.memoize_positions()` come `routes_copilot` per non rileggere le posizioni a ogni blocco.

#### `copilot/structured.py` (TASK-62)

```python
STRUCTURED_OUTPUT_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "gemini", "openrouter"})

class StructuredOutputError(Exception):
    code: str = "structured_error"
    def __init__(self, message: str, *, provider: str) -> None: ...   # attributi: .provider, .code
class StructuredOutputUnavailable(StructuredOutputError):   code = "unsupported_provider"
class StructuredOutputTimeout(StructuredOutputError):       code = "timeout"
class StructuredOutputProviderError(StructuredOutputError): code = "provider_error"
class StructuredOutputSchemaError(StructuredOutputError):   code = "schema_mismatch"

def supports_structured_output(config: CopilotConfig) -> bool

def call_structured(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],      # [{"role": "user" | "assistant", "content": str}]
    schema: dict[str, Any],              # JSON Schema (sottoinsieme di api-contracts §6.4)
    *,
    schema_name: str,                    # "tribunal_opening" | "tribunal_rebuttal" | "tribunal_synthesis" | …
    timeout_s: float = 45.0,             # per tentativo
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """dict conforme a `schema` (validato con jsonschema Draft 2020-12 sullo schema completo).
    Una risposta non conforme → un solo nuovo tentativo, poi StructuredOutputSchemaError.
    Provider senza supporto (local) → StructuredOutputUnavailable senza chiamare la rete."""
```

Meccanismo per provider: OpenAI e OpenRouter con tool forzato
(`tools=[{"type": "function", "function": {"name": schema_name, "parameters": schema}}]`,
`tool_choice={"type": "function", "function": {"name": schema_name}}`); OpenAI **senza**
`base_url` esplicito (così `OPENAI_BASE_URL` del finto LLM degli E2E funziona), OpenRouter con
`base_url="https://openrouter.ai/api/v1"` come `providers.py`. Anthropic con
`tools=[{"name": schema_name, "input_schema": schema}]`, `tool_choice={"type": "tool", "name":
schema_name}`. Gemini con output strutturato nativo (`response_mime_type="application/json"` e
schema), togliendo dallo schema inviato le parole chiave che Gemini rifiuta
(`additionalProperties` incluso, se la versione dell'SDK lo rifiuta) ma validando sempre la
risposta con lo schema completo. `providers.py` non cambia.

#### `services/tribunal/personas.py` (TASK-63)

```python
VOICE_IDS: tuple[str, ...] = ("indicizzatore", "fattoriale", "prudente")   # ordine canonico
THEMES: tuple[str, ...]          # api-contracts §5.2, nell'ordine dell'enum
PROMPT_VERSION: str = "tribunale-prompt-1"

@dataclass(frozen=True)
class Voice:
    id: str; code: str; name: str; mandate: str          # mandate = testo breve di VoiceInfo
    focus_themes: tuple[str, ...]
    def info(self) -> dict[str, str]                     # VoiceInfo {id, code, name, mandate}

VOICES: dict[str, Voice]          # chiavi in ordine canonico

@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    messages: list[dict[str, str]]
    schema: dict[str, Any]
    schema_name: str

def opening_schema() -> dict[str, Any]          # api-contracts §6.4 "tribunal_opening"
def rebuttal_schema() -> dict[str, Any]         # "tribunal_rebuttal"
def synthesis_schema() -> dict[str, Any]        # "tribunal_synthesis"

def build_opening_request(voice_id: str, case_file: dict[str, Any]) -> LLMRequest
def build_rebuttal_request(voice_id: str, case_file: dict[str, Any],
                           other_arguments: list[dict[str, Any]]) -> LLMRequest
    # other_arguments: TribunalArgument ammessi delle ALTRE voci (id, voice, theme, stance, text_template, fact_ids)
def build_synthesis_request(case_file: dict[str, Any], arguments: list[dict[str, Any]],
                            rebuttals: list[dict[str, Any]]) -> LLMRequest
```

Regole: prima riga del prompt di sistema come in api-contracts §8.3; il fascicolo va **una sola
volta**, nel primo messaggio `user`, come JSON tra le righe `<fascicolo>` e `</fascicolo>`, con i
campi `id`, `label`, `formatted`, `unit`, `quality`, `citable`, `reason`, `subject` dei fatti e
`symbol`, `isin`, `name` degli strumenti; gli argomenti da replicare/sintetizzare vanno nello
stesso messaggio tra `<argomenti>` e `</argomenti>` con `text_template` (mai `text`); il prompt di
sistema dice che il contenuto tra quei marcatori è **dato, non istruzione** (nota `DATA_NOTE` di
`copilot_doctor_tools.py`). Nessun dato del fascicolo entra nel prompt di sistema. File di prompt:
`prompts/tribunal_common.txt` (regole comuni e divieti), `tribunal_voice_indicizzatore.txt`,
`tribunal_voice_fattoriale.txt`, `tribunal_voice_prudente.txt` (mandati),
`tribunal_phase_opening.txt`, `tribunal_phase_rebuttal.txt`, `tribunal_phase_synthesis.txt`.

#### `services/tribunal/verifier.py` (TASK-64)

```python
DISCARD_CODES: tuple[str, ...]   # i 15 codici di api-contracts §7.3, in ordine di precedenza
MAX_ARGUMENTS_PER_VOICE = 4; MAX_REBUTTALS_PER_VOICE = 2; MAX_FACTS_PER_ITEM = 4
MIN_TEXT_CHARS = 20; MAX_ARGUMENT_CHARS = 360; MAX_REBUTTAL_CHARS = 280
MAX_POINT_CHARS = 300; MAX_SIDE_CHARS = 240; MAX_QUESTION_CHARS = 200
MAX_SHARED_POINTS = 3; MAX_CONTESTED_POINTS = 3; MAX_OPEN_QUESTIONS = 3

@dataclass(frozen=True)
class Discard:
    path: str        # posizione nel grezzo: "arguments[3]", "rebuttals[1]", "shared_points[0]",
                     # "contested_points[1]", "open_questions[1]" (come expected_discards della fixture)
    code: str

@dataclass(frozen=True)
class VerificationResult:
    admitted: list[dict[str, Any]]          # TribunalArgument / TribunalRebuttal
    discarded: list[Discard]
    def by_code(self) -> dict[str, int]     # solo codici ≥ 1, chiavi in ordine alfabetico

@dataclass(frozen=True)
class SynthesisVerification:
    synthesis: dict[str, Any]               # TribunalSynthesis
    discarded: list[Discard]
    def by_code(self) -> dict[str, int]
    @property
    def admitted_count(self) -> int         # punti condivisi + contesi + domande

def normalize_text(text: str) -> str                                   # api-contracts §7.1
def render_template(template: str, case_file: Mapping[str, Any]) -> str  # {Fn} → formatted
def verify_opening(voice_id: str, raw: Mapping[str, Any], case_file: Mapping[str, Any]) -> VerificationResult
def verify_rebuttals(voice_id: str, raw: Mapping[str, Any], case_file: Mapping[str, Any],
                     arguments: list[dict[str, Any]]) -> VerificationResult
    # arguments: TUTTI gli argomenti ammessi in apertura (anche della stessa voce: li esclude lui)
def verify_synthesis(raw: Mapping[str, Any], case_file: Mapping[str, Any],
                     arguments: list[dict[str, Any]], rebuttals: list[dict[str, Any]]) -> SynthesisVerification
```

`raw` è il dict restituito da `call_structured` (`{"arguments": [...]}` ecc.). Funzioni pure:
nessun I/O, nessun log del testo, nessuna lettura di configurazione.

#### `services/tribunal/orchestrator.py` (TASK-65; TASK-66 cambia solo `_default_store`)

```python
CALL_TIMEOUT_S = 45
SESSION_TIMEOUT_S = 180
KeySource = Literal["user", "server"]

@dataclass(frozen=True)
class TribunalConfig:
    config: CopilotConfig
    key_source: KeySource

def resolve_tribunal_config(settings: Any, repo: Any, user_id: str) -> TribunalConfig | None
def sse_event(event_type: str, content: dict[str, Any]) -> str        # api-contracts §9.1

class SessionStore(Protocol):
    def get_latest(self, user_id: str, scope_fingerprint: str) -> dict[str, Any] | None   # TribunalSession
    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *,
             key_source: KeySource) -> None        # sovrascrive l'ultima; conta l'uso se key_source == "server"
    def count_today(self, user_id: str, *, now: datetime | None = None) -> int   # sedute server di oggi (Europe/Rome)

class NullSessionStore:   # get_latest → None, save → no-op, count_today → 0
    ...

def _default_store(repo: Any) -> SessionStore     # TASK-65: NullSessionStore(); TASK-66: TribunalStore(repo.engine)

StructuredCall = Callable[..., dict[str, Any]]      # stessa firma di structured.call_structured

class TribunalOrchestrator:
    def __init__(self, repo: Any, settings: Any, *, store: SessionStore | None = None,
                 llm_call: StructuredCall | None = None,            # default call_structured; i test passano un finto
                 service_getter: Callable[[], Any] | None = None) -> None
    def status(self, user_id: str, portfolio_ids: list[Any]) -> dict[str, Any]          # TribunalStatus
    def latest(self, user_id: str, portfolio_ids: list[Any]) -> dict[str, Any]          # TribunalLatestResponse
    def start(self, user_id: str, portfolio_ids: list[Any], *, force_new: bool = False) -> Iterator[str]
        """Esegue i controlli 1-7 di api-contracts §3.2 SUBITO (solleva AppError, prima di
        restituire) e poi restituisce il generatore SSE (dal vivo o riproduzione)."""
```

Il flag `doctor_tribunal_enabled` è controllato dalle route (404 `feature_disabled`); il servizio
non lo rilegge.

#### `services/tribunal/store.py` (TASK-66)

```python
class TribunalStore:            # implementa SessionStore
    def __init__(self, engine: Engine) -> None
    def get_latest(self, user_id: str, scope_fingerprint: str) -> dict[str, Any] | None
    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *, key_source: KeySource) -> None
    def count_today(self, user_id: str, *, now: datetime | None = None) -> int
    def delete_for_user(self, user_id: str) -> int     # per la cancellazione dell'account
```

Persistenza (indicativa, la decide TASK-66 nel rispetto dei requisiti): una riga per
`(owner_user_id, scope_fingerprint)` con `case_file_hash` e `contract_version` in chiaro, la
seduta JSON **cifrata a livello di campo** con la DEK dell'utente (`app/crypto/`), `key_source`,
`created_at`; una tabella dei membri dello scope con FK su `portfolios(id) on delete cascade` e
pulizia della seduta quando un membro sparisce; un contatore per `(owner_user_id, giorno
Europe/Rome)`. RLS attiva senza policy, come le tabelle del Doctor.

#### `api/routes_tribunal.py` (TASK-65)

```python
def register_tribunal_routes(
    router: APIRouter, repo: Any, *, settings: Any,
    orchestrator_getter: Callable[[], TribunalOrchestrator] | None = None,
) -> None
```

Registrata in `app/main.py` **dopo** `register_doctor_routes` e **prima** di
`register_portfolio_health_routes`. Riusa da `routes_doctor.py` (import, nessuna modifica):
`DoctorRoute`, `request_id_of`, `_query_ids`, `_parse`, `_with_request_id`.

## 3. Moduli frontend — `src/frontend/valore-frontend/src/`

### 3.1 Dati (TASK-67)

`services/api/tribunalTypes.ts` — tipi 1:1 con il contratto (stessi nomi di campo, snake_case):

```ts
export type TribunalVoiceId = 'indicizzatore' | 'fattoriale' | 'prudente';
export const TRIBUNAL_VOICE_IDS: readonly TribunalVoiceId[];   // ordine canonico
export type TribunalPhase = 'apertura' | 'replica' | 'sintesi';
export type TribunalTheme = 'costi' | 'diversificazione' | 'concentrazione' | 'composizione'
  | 'esposizione_geografica' | 'esposizione_settoriale' | 'rischio' | 'scenari' | 'regole_personali' | 'qualita_dati';
export type TribunalStance = 'punto_di_forza' | 'criticita' | 'neutro';
export type TribunalRebuttalStance = 'concorda' | 'contesta' | 'precisa';
export type TribunalFactUnit = 'pct' | 'score' | 'count' | 'index' | 'months' | 'text';
export type TribunalFactGroup = 'composizione' | 'concentrazione' | 'costi' | 'salute' | 'esposizione' | 'stress' | 'scenari' | 'regole';
export type TribunalFactSource = 'doctor_metrics' | 'positions' | 'health_score' | 'health_alerts' | 'xray' | 'stress_test' | 'monte_carlo' | 'doctor_policy';
export type TribunalFactQuality = 'ok' | 'partial' | 'stale' | 'missing';
export type TribunalDiscardCode = 'schema_non_valido' | 'riferimento_non_ammesso' | 'nessun_fatto' | 'troppi_fatti'
  | 'fatto_inesistente' | 'fatto_non_citabile' | 'segnaposto_malformato' | 'segnaposto_non_citato' | 'fatto_estraneo'
  | 'testo_troppo_lungo' | 'strumento_non_ammesso' | 'cifra_libera' | 'indicazione_operativa' | 'verdetto' | 'troppi_argomenti';
export type TribunalStatusReason = 'copilot_not_configured' | 'provider_not_supported' | 'daily_limit_reached';
export type TribunalStreamErrorCode = 'timeout' | 'too_few_voices' | 'synthesis_failed' | 'internal_error';
export type TribunalVoiceErrorCode = 'timeout' | 'schema_mismatch' | 'provider_error' | 'unsupported_provider';

export interface TribunalScope { portfolio_ids: number[]; scope_type: 'single' | 'aggregate'; fingerprint: string }
export interface TribunalFact { id: string; key: string; group: TribunalFactGroup; label: string;
  value: number | string | null; unit: TribunalFactUnit; formatted: string; source: TribunalFactSource;
  quality: TribunalFactQuality; citable: boolean; reason: string | null; subject: string | null; sensitive: boolean }
export interface TribunalInstrument { symbol: string; isin: string | null; name: string }
export interface TribunalCaseFile { schema_version: 1; contract_version: string; status: 'ready' | 'empty_portfolio';
  scope: TribunalScope; generated_at: string; as_of: string | null; methodology_version: string; hash: string;
  instruments: TribunalInstrument[]; facts: TribunalFact[]; counts: { total: number; citable: number }; notes: string[] }
export interface TribunalVoiceInfo { id: TribunalVoiceId; code: 'IND' | 'FAT' | 'PRU'; name: string; mandate: string }
export interface TribunalArgument { id: string; voice: TribunalVoiceId; phase: 'apertura'; theme: TribunalTheme;
  stance: TribunalStance; text: string; text_template: string; fact_ids: string[] }
export interface TribunalRebuttal { id: string; voice: TribunalVoiceId; phase: 'replica'; target_argument_id: string;
  target_voice: TribunalVoiceId; stance: TribunalRebuttalStance; text: string; text_template: string; fact_ids: string[] }
export interface TribunalSharedPoint { id: string; text: string; text_template: string; fact_ids: string[];
  argument_ids: string[]; voices: TribunalVoiceId[] }
export interface TribunalContestedSide { voices: TribunalVoiceId[]; argument_ids: string[]; summary: string;
  summary_template: string; fact_ids: string[] }
export interface TribunalContestedPoint { id: string; text: string; text_template: string; fact_ids: string[];
  metric_codes: string[]; sides: [TribunalContestedSide, TribunalContestedSide] }
export interface TribunalOpenQuestion { id: string; text: string }
export interface TribunalSynthesis { shared_points: TribunalSharedPoint[]; contested_points: TribunalContestedPoint[];
  open_questions: TribunalOpenQuestion[] }
export interface TribunalDiscardSummary { phase: TribunalPhase; voice: TribunalVoiceId | null; admitted: number;
  discarded: number; by_code: Partial<Record<TribunalDiscardCode, number>> }
export interface TribunalVoiceError { phase: TribunalPhase; voice: TribunalVoiceId; code: TribunalVoiceErrorCode;
  message: string; retryable?: boolean }
export interface TribunalTotals { arguments: number; rebuttals: number; shared_points: number; contested_points: number;
  open_questions: number; discarded: number }
export interface TribunalSessionStart { session_id: string; scope: TribunalScope; reused: boolean; created_at: string;
  contract_version: string; prompt_version: string; provider: string; model: string; voices: TribunalVoiceInfo[] }
export interface TribunalSession { session_id: string; scope: TribunalScope; created_at: string; completed_at: string;
  contract_version: string; prompt_version: string; provider: string; model: string; voices: TribunalVoiceInfo[];
  case_file: TribunalCaseFile; arguments: TribunalArgument[]; rebuttals: TribunalRebuttal[]; synthesis: TribunalSynthesis;
  discarded: TribunalDiscardSummary[]; voice_errors: TribunalVoiceError[]; totals: TribunalTotals }
export interface TribunalStatus { available: boolean; reason: TribunalStatusReason | null; message: string | null;
  provider: string | null; model: string | null; key_source: 'user' | 'server' | null;
  limit: { daily_limit: number; used_today: number; remaining: number; resets_at: string } | null; scope: TribunalScope }
export interface TribunalLatestResponse { session: TribunalSession | null; current_case_file_hash: string | null;
  data_changed: boolean | null }
export interface TribunalStreamError { code: TribunalStreamErrorCode; message: string; retryable: boolean; phase: TribunalPhase | null }
export interface TribunalDone { session_id: string; reused: boolean; saved: boolean; duration_ms: number; totals: TribunalTotals }
export type TribunalEvent =
  | { type: 'session'; content: TribunalSessionStart }
  | { type: 'case_file'; content: TribunalCaseFile }
  | { type: 'phase'; content: { phase: TribunalPhase; status: 'started' | 'completed' } }
  | { type: 'argument'; content: TribunalArgument }
  | { type: 'rebuttal'; content: TribunalRebuttal }
  | { type: 'discarded'; content: TribunalDiscardSummary }
  | { type: 'voice_error'; content: TribunalVoiceError }
  | { type: 'synthesis'; content: TribunalSynthesis }
  | { type: 'done'; content: TribunalDone }
  | { type: 'error'; content: TribunalStreamError };
```

Esportati da `services/api/index.ts` (`export * from './tribunalTypes'; export * from './tribunal';`).
In `services/api/types.ts` TASK-67 aggiunge solo `tribunal_enabled?: boolean` a `DoctorFeatures`.

`services/api/tribunal.ts`:

```ts
export const getTribunalStatus: (portfolioIds: number[]) => Promise<TribunalStatus>;
  // GET /doctor/tribunal/status?<doctorScopeQuery>
export function getLatestTribunalSession(portfolioIds: number[]): Promise<TribunalLatestResponse | null>;
  // null se l'endpoint non esiste (404 con error.code assente); rilancia ApiRequestError per not_found/feature_disabled
export function parseTribunalEvent(payload: string): TribunalEvent | null;
  // JSON.parse + controllo di forma minimo: type noto e content oggetto, altrimenti null
export function streamTribunalSession(options: {
  portfolioIds: number[]; forceNew?: boolean; signal?: AbortSignal;
  onEvent: (event: TribunalEvent) => void; fetchImpl?: typeof fetch;
}): Promise<void>;
  // POST /doctor/tribunal/sessions con lo stesso token di apiFetch (getAuthToken);
  // risposta non 2xx → ApiRequestError (corpo letto come apiFetch); si risolve a fine stream;
  // l'abort rigetta con l'AbortError di fetch
```

`components/doctor/tribunal/useTribunalSession.ts`:

```ts
export type TribunalRunStatus = 'idle' | 'running' | 'completed' | 'error' | 'limit_reached' | 'aborted';
export interface TribunalClientError { code: string; message: string; retryable: boolean;
  phase: TribunalPhase | null; resetsAt: string | null; httpStatus: number | null }
  // code: codici HTTP (§3.4) o SSE (§9.3.10), oppure lato client 'stream_interrupted' | 'network_error'
export interface TribunalSessionState {
  status: TribunalRunStatus;
  phase: TribunalPhase | null;               // fase in corso
  completedPhases: TribunalPhase[];
  sessionId: string | null; reused: boolean; createdAt: string | null;
  voices: TribunalVoiceInfo[];
  caseFile: TribunalCaseFile | null;
  argumentsByVoice: Record<TribunalVoiceId, TribunalArgument[]>;
  rebuttals: TribunalRebuttal[];
  synthesis: TribunalSynthesis | null;
  discarded: { total: number; byVoice: Record<TribunalVoiceId, number>; synthesis: number;
               byCode: Partial<Record<TribunalDiscardCode, number>> };
  voiceErrors: TribunalVoiceError[];
  totals: TribunalTotals | null;
  error: TribunalClientError | null;
}
export const initialTribunalState: TribunalSessionState;
export function reduceTribunalEvent(state: TribunalSessionState, event: TribunalEvent): TribunalSessionState;  // pura
export function sessionToState(session: TribunalSession): TribunalSessionState;   // seduta salvata → stato 'completed', reused true
export interface UseTribunalSessionResult extends TribunalSessionState {
  start: () => void;        // forceNew false
  redo: () => void;         // forceNew true («Rifai la seduta»)
  stop: () => void;         // abort della connessione → status 'aborted', contenuto conservato
  loadSaved: (session: TribunalSession) => void;
  reset: () => void;
}
export function useTribunalSession(portfolioIds: number[]): UseTribunalSessionResult;
  // cambio di fingerprint o smontaggio → abort + reset; un nuovo start annulla lo stream precedente
export const tribunalQueryKeys: { status: (fingerprint: string) => readonly unknown[]; latest: (fingerprint: string) => readonly unknown[] };
export function useTribunalFeature(): { isLoading: boolean; enabled: boolean };
  // useQuery con doctorQueryKeys.features + getDoctorFeatures (cache condivisa con useDoctorFeatures): data?.tribunal_enabled === true
export function useTribunalStatus(portfolioIds: number[], enabled: boolean): UseQueryResult<TribunalStatus>;
export function useTribunalLatest(portfolioIds: number[], enabled: boolean): UseQueryResult<TribunalLatestResponse | null>;
```

Transizioni dello stato: `start`/`redo` → `running` (stato azzerato); `session` imposta id e
voci; `phase started` imposta `phase`; `phase completed` lo aggiunge a `completedPhases`; `done`
→ `completed` (+ invalida `tribunalQueryKeys.status` e `.latest` dello scope); `error` SSE →
`error` conservando tutto; HTTP 429 `daily_limit_reached` → `limit_reached` con `resetsAt`;
altro HTTP non 2xx → `error`; fine dello stream senza `done`/`error` → `error`
`stream_interrupted`; `stop` → `aborted`. Eventi sconosciuti o malformati non cambiano lo stato.

Fixture (`components/doctor/tribunal/fixtures/`): `seduta-esempio.json` e
`seduta-esempio.sse.txt` copiati **senza modifiche** da `docs/tribunale/fixtures/`, e `index.ts`:

```ts
export const tribunalSessionFixture: TribunalSession;          // fixture.session
export const tribunalEventsFixture: TribunalEvent[];           // eventi del .sse.txt (import '?raw' + parseTribunalEvent)
export function createFakeTribunalResponse(events: TribunalEvent[] | string,
  options?: { chunkSize?: number; failAfterEvents?: number; status?: number; errorBody?: unknown }): Response;
export function createFakeTribunalFetch(responseFactory: () => Response): typeof fetch;
```

### 3.2 Interfaccia (TASK-68)

Tutto in `components/doctor/tribunal/`, esclusi `useTribunalSession.ts`, `fixtures/` (TASK-67) e
i file di TASK-70. Componente d'ingresso:

```ts
export interface TribunalSectionProps {
  portfolioIds: number[];
  isAggregate: boolean;
  privacy: boolean;
  /** Slot per le azioni di un punto conteso (TASK-70); assente = nessuna azione. */
  renderContestedActions?: (point: TribunalContestedPoint,
                            context: { caseFile: TribunalCaseFile; voices: TribunalVoiceInfo[] }) => ReactNode;
}
export function TribunalSection(props: TribunalSectionProps): JSX.Element;
```

Gli altri componenti e la loro struttura sono in `ui-spec.md` §3.

### 3.3 Pagina (TASK-69) e azioni (TASK-70)

- TASK-69: `pages/Doctor.page.tsx` aggiunge `'tribunale'` a `DOCTOR_SECTIONS` (ultima),
  `?section=tribunale`, visibile se `DOCTOR_TRIBUNAL_UI_ENABLED` (nuovo in `src/features.ts`) **e**
  `useTribunalFeature().enabled`; monta
  `<DoctorSectionErrorBoundary key={`tribunale-${scopeKeyString}`} area="Tribunale"><TribunalSection portfolioIds={scopeIds} isAggregate={isAggregate} privacy={privacy} /></DoctorSectionErrorBoundary>`.
- TASK-70: `components/doctor/tribunal/TribunalContestedActions.tsx`:

  ```ts
  export interface TribunalContestedActionsProps {
    point: TribunalContestedPoint; caseFile: TribunalCaseFile; voices: TribunalVoiceInfo[];
    isAggregate: boolean; privacy: boolean;
    copilotAvailable: boolean; parametriEnabled: boolean; labEnabled: boolean;
    onAskCopilot: (text: string) => void;          // Doctor.page: handleAskCopilot
    onOpenPolicyDraft: (metricCode: string) => void;
    onOpenLab: () => void;
  }
  export function TribunalContestedActions(props: TribunalContestedActionsProps): JSX.Element | null;
  export function buildContestedCopilotPrompt(point: TribunalContestedPoint, caseFile: TribunalCaseFile,
                                              voices: TribunalVoiceInfo[],
                                              options?: { privacy?: boolean }): string;   // testo in ui-spec §9
  ```

  e in `Doctor.page.tsx` passa `renderContestedActions` a `TribunalSection` (dopo TASK-69).

## 4. Proprietà dei file (task → file)

Un file ha un solo task proprietario; le eccezioni sono elencate e minime.

| task | file di proprietà | note |
|---|---|---|
| TASK-60 | `docs/tribunale/api-contracts.md`, `architecture.md`, `ui-spec.md`, `fixtures/seduta-esempio.json`, `fixtures/seduta-esempio.sse.txt` | gli altri task aggiungono solo la propria sezione «Deviazioni» in `api-contracts.md` |
| TASK-61 | `src/backend/app/services/tribunal/__init__.py`, `case_file.py`, `src/backend/tests/unit/test_tribunal_case_file.py` | |
| TASK-62 | `src/backend/app/copilot/structured.py`, `src/backend/tests/unit/test_copilot_structured.py` | `providers.py` invariato; un helper condiviso eventuale senza cambiare firme |
| TASK-63 | `src/backend/app/services/tribunal/personas.py`, `src/backend/app/prompts/tribunal_*.txt`, `src/backend/tests/unit/test_tribunal_personas.py` | fixture del contratto, non il modulo di TASK-61 |
| TASK-64 | `src/backend/app/services/tribunal/verifier.py`, `src/backend/tests/unit/test_tribunal_verifier.py` | fixture del contratto |
| TASK-65 | `src/backend/app/services/tribunal/orchestrator.py`, `src/backend/app/api/routes_tribunal.py`, registrazione in `src/backend/app/main.py`, `doctor_tribunal_enabled` e `doctor_tribunal_daily_limit` in `src/backend/app/config.py`, `src/backend/.env.example`, `src/backend/tests/unit/test_tribunal_orchestrator.py`, `src/backend/tests/unit/test_tribunal_routes.py` | **eccezione**: aggiunge `tribunal_enabled` a `DoctorFeaturesRead` (`app/schemas/doctor_policy.py`) e a `DoctorPolicyService.features` (`doctor_policy/service.py`), una riga ciascuno |
| TASK-66 | `src/backend/app/services/tribunal/store.py`, `database/migrations/<data>_tribunal_sessions.sql` (+ copia in `app/sql/migrations/` se serve all'avvio, come il Doctor 2.0), modifiche a `database/schema.sql` e `database/supabase_full_setup.sql`, `src/backend/tests/unit/test_tribunal_store.py`, `src/backend/tests/integration/test_tribunal_store_postgres.py` | modifiche minime a `orchestrator.py` (`_default_store`) e `routes_tribunal.py` |
| TASK-67 | `src/frontend/valore-frontend/src/services/api/tribunal.ts`, `services/api/tribunalTypes.ts`, le due righe di export in `services/api/index.ts`, `tribunal_enabled?` in `DoctorFeatures` (`services/api/types.ts`), `components/doctor/tribunal/useTribunalSession.ts`, `components/doctor/tribunal/fixtures/`, test `services/api/tribunal.test.ts`, `components/doctor/tribunal/useTribunalSession.test.ts` | |
| TASK-68 | `src/frontend/valore-frontend/src/components/doctor/tribunal/` (tutto il resto: componenti, `tribunalFormat.ts`, `Tribunal.test.tsx`) | non tocca `Doctor.page.tsx` |
| TASK-69 | `src/frontend/valore-frontend/src/pages/Doctor.page.tsx`, `src/pages/Doctor.tribunal.test.tsx`, `DOCTOR_TRIBUNAL_UI_ENABLED` in `src/features.ts` | unico task del Tribunale che modifica `Doctor.page.tsx` prima di TASK-70 |
| TASK-70 | `components/doctor/tribunal/TribunalContestedActions.tsx`, `components/doctor/tribunal/TribunalContestedActions.test.tsx`, agganci in `Doctor.page.tsx` | dopo TASK-69 |
| TASK-71 | `scripts/e2e/tribunal_*`, `src/backend/tests/integration/test_tribunal_adversarial.py`, `README.md`, `CHANGELOG.md`, `docs/tribunale/test-report.md` | unico che tocca README e CHANGELOG; corregge i difetti nei moduli che li contengono, segnalandolo |

Ordine e parallelismo:

```
TASK-60 ─┬─ TASK-61 ─┐
         ├─ TASK-62 ─┤
         ├─ TASK-63 ─┼─ TASK-65 ── TASK-66 ─┐
         ├─ TASK-64 ─┘                       │
         └─ TASK-67 ── TASK-68 ── TASK-69 ── TASK-70 ── TASK-71
```

TASK-69 può partire senza TASK-66 (la parte «ultima seduta» degrada, api-contracts §3.3).

## 5. Configurazione

| impostazione | env | default | effetto |
|---|---|---|---|
| `doctor_tribunal_enabled` | `DOCTOR_TRIBUNAL_ENABLED` | `true` | `false` → endpoint `/doctor/tribunal/*` 404 `feature_disabled`, `tribunal_enabled: false` in `/doctor/features` |
| `doctor_tribunal_daily_limit` | `DOCTOR_TRIBUNAL_DAILY_LIMIT` | `3` | sedute nuove al giorno con la chiave del server; `0` = solo con chiave propria |
| (frontend) `DOCTOR_TRIBUNAL_UI_ENABLED` | `src/features.ts` | `true` | kill switch UI |

Provider e chiavi sono quelli del Copilot (`COPILOT_PROVIDER`, `*_API_KEY`, chiave utente
cifrata): nessuna configurazione LLM nuova.

## 6. Sicurezza e privacy

- **Scope mai dal modello**: arriva dalla route, è verificato con `resolve_scope` a ogni
  richiesta; un portafoglio non posseduto è 404 come nel Doctor.
- **Niente importi al modello**: il fascicolo non contiene valori in valuta (api-contracts §4.1).
- **Testi come dati**: nomi di strumenti, etichette e note sono ripuliti (`clean_text`) e passati
  tra marcatori come dati; il prompt di sistema non contiene dati del fascicolo (TASK-63 AC #5;
  prova avversaria in TASK-71).
- **Verificatore prima dell'utente**: nessun testo del modello raggiunge il frontend, i log o il
  database senza essere passato dal verificatore; gli scartati non escono dal backend.
- **Log** (`logger = logging.getLogger("app.services.tribunal")`): solo conteggi, durate e
  codici. Formato:
  `tribunal.phase scope_size=%d phase=%s voice=%s admitted=%d discarded=%d codes=%s ms=%d`,
  `tribunal.session scope_size=%d reused=%d key_source=%s outcome=%s ms=%d`. Mai fascicolo,
  testi, prompt, nomi, ISIN, chiavi o eccezioni del provider con payload (`logger.warning` con
  il nome della classe dell'eccezione, non `logger.exception` con il messaggio).
- **Costo**: lock di una seduta per utente, limite giornaliero sulla chiave del server, riuso a
  fascicolo invariato, timeout di seduta.
- **Persistenza**: solo sedute concluse, cifrate a livello di campo, cancellate con il
  portafoglio o l'utente.

## 7. Test

| livello | dove | cosa |
|---|---|---|
| unit backend | `tests/unit/test_tribunal_*.py`, `test_copilot_structured.py` | per modulo; personas e verificatore usano `docs/tribunale/fixtures/seduta-esempio.json` (percorso dalla radice del repo: `Path(__file__).resolve().parents[4] / "docs/tribunale/fixtures"`; se manca il test fallisce, non salta) |
| verificatore | `test_tribunal_verifier.py` | dato `raw` e `case_file` della fixture, gli ammessi coincidono con `session.arguments/rebuttals/synthesis` e gli scarti con `expected_discards` (path e codice); più un caso per ogni codice |
| orchestratore | `test_tribunal_orchestrator.py` | `llm_call` finto che restituisce `raw` della fixture → la sequenza di eventi rispetta api-contracts §9.2 e i contenuti coincidono con la fixture (a parte l'ordine di completamento) |
| frontend | Vitest | reducer su `tribunalEventsFixture`, componenti su `tribunalSessionFixture` |
| avversari ed E2E | TASK-71 | finto LLM OpenAI-compatibile (`OPENAI_BASE_URL`), che riconosce fase e voce dalla prima riga del prompt di sistema (api-contracts §8.3) |

## 8. Perché il Tribunale non è consulenza personalizzata

La consulenza in materia di investimenti (MiFID II, art. 4 n. 4; TUF art. 1 c. 5-septies) è una
**raccomandazione personalizzata riguardante una o più operazioni su strumenti finanziari
determinati**, presentata come adatta al cliente. Il Tribunale è costruito per non esserlo:

1. **Nessuna operazione**: il verificatore scarta ogni indicazione di comprare, vendere,
   sostituire, liquidare o ribilanciare (api-contracts §7.6); le azioni dei punti contesi
   portano solo a strumenti dell'utente (Copilot per spiegare, I miei parametri con una bozza
   **senza soglie** da confermare, Laboratorio per simulare) e non propongono strumenti né soglie
   (TASK-70).
2. **Nessuno strumento nuovo**: nessun ISIN, ticker o emittente fuori dal portafoglio può
   comparire (api-contracts §7.5).
3. **Nessuna valutazione di adeguatezza**: il Tribunale non conosce obiettivi, orizzonte,
   situazione finanziaria né tolleranza al rischio dell'utente e non li chiede; il linguaggio di
   adeguatezza è scartato. Le domande aperte restituiscono all'utente proprio queste scelte.
4. **Nessun verdetto**: tre letture con mandati dichiarati e opposti, nessun vincitore, nessun
   punteggio tra le voci (§7.7 del contratto, `ui-spec.md` §7). È materiale per ragionare, non
   un'indicazione.
5. **Solo fatti già calcolati**: ogni numero viene dal Doctor, con fonte e qualità visibili;
   l'AI non produce dati.

L'avvertenza sempre visibile (`ui-spec.md` §5) lo dice all'utente con parole semplici.
