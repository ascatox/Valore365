// Tribunale del portafoglio — tipi 1:1 con il contratto
// (docs/tribunale/api-contracts.md §3, §4, §5, §6, §8.7, §9; firme in architecture.md §3.1).
// Stessi nomi di campo del backend (snake_case).

export type TribunalVoiceId = 'indicizzatore' | 'fattoriale' | 'prudente';
/** Ordine canonico delle voci (visualizzazione, riproduzione, totali). */
export const TRIBUNAL_VOICE_IDS: readonly TribunalVoiceId[] = ['indicizzatore', 'fattoriale', 'prudente'];
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

export interface TribunalScope {
  portfolio_ids: number[];
  scope_type: 'single' | 'aggregate';
  fingerprint: string;
}

export interface TribunalFact {
  id: string;
  key: string;
  group: TribunalFactGroup;
  label: string;
  value: number | string | null;
  unit: TribunalFactUnit;
  formatted: string;
  source: TribunalFactSource;
  quality: TribunalFactQuality;
  citable: boolean;
  reason: string | null;
  subject: string | null;
  sensitive: boolean;
}

export interface TribunalInstrument {
  symbol: string;
  isin: string | null;
  name: string;
}

export interface TribunalCaseFile {
  schema_version: 1;
  contract_version: string;
  status: 'ready' | 'empty_portfolio';
  scope: TribunalScope;
  generated_at: string;
  as_of: string | null;
  methodology_version: string;
  hash: string;
  instruments: TribunalInstrument[];
  facts: TribunalFact[];
  counts: { total: number; citable: number };
  notes: string[];
}

export interface TribunalVoiceInfo {
  id: TribunalVoiceId;
  code: 'IND' | 'FAT' | 'PRU';
  name: string;
  mandate: string;
}

export interface TribunalArgument {
  id: string;
  voice: TribunalVoiceId;
  phase: 'apertura';
  theme: TribunalTheme;
  stance: TribunalStance;
  text: string;
  text_template: string;
  fact_ids: string[];
}

export interface TribunalRebuttal {
  id: string;
  voice: TribunalVoiceId;
  phase: 'replica';
  target_argument_id: string;
  target_voice: TribunalVoiceId;
  stance: TribunalRebuttalStance;
  text: string;
  text_template: string;
  fact_ids: string[];
}

export interface TribunalSharedPoint {
  id: string;
  text: string;
  text_template: string;
  fact_ids: string[];
  argument_ids: string[];
  voices: TribunalVoiceId[];
}

export interface TribunalContestedSide {
  voices: TribunalVoiceId[];
  argument_ids: string[];
  summary: string;
  summary_template: string;
  fact_ids: string[];
}

export interface TribunalContestedPoint {
  id: string;
  text: string;
  text_template: string;
  fact_ids: string[];
  metric_codes: string[];
  sides: [TribunalContestedSide, TribunalContestedSide];
}

export interface TribunalOpenQuestion {
  id: string;
  text: string;
}

export interface TribunalSynthesis {
  shared_points: TribunalSharedPoint[];
  contested_points: TribunalContestedPoint[];
  open_questions: TribunalOpenQuestion[];
}

export interface TribunalDiscardSummary {
  phase: TribunalPhase;
  voice: TribunalVoiceId | null;
  admitted: number;
  discarded: number;
  by_code: Partial<Record<TribunalDiscardCode, number>>;
}

export interface TribunalVoiceError {
  phase: TribunalPhase;
  voice: TribunalVoiceId;
  code: TribunalVoiceErrorCode;
  message: string;
  retryable?: boolean;
}

export interface TribunalTotals {
  arguments: number;
  rebuttals: number;
  shared_points: number;
  contested_points: number;
  open_questions: number;
  discarded: number;
}

export interface TribunalSessionStart {
  session_id: string;
  scope: TribunalScope;
  reused: boolean;
  created_at: string;
  contract_version: string;
  prompt_version: string;
  provider: string;
  model: string;
  voices: TribunalVoiceInfo[];
}

export interface TribunalSession {
  session_id: string;
  scope: TribunalScope;
  created_at: string;
  completed_at: string;
  contract_version: string;
  prompt_version: string;
  provider: string;
  model: string;
  voices: TribunalVoiceInfo[];
  case_file: TribunalCaseFile;
  arguments: TribunalArgument[];
  rebuttals: TribunalRebuttal[];
  synthesis: TribunalSynthesis;
  discarded: TribunalDiscardSummary[];
  voice_errors: TribunalVoiceError[];
  totals: TribunalTotals;
}

export interface TribunalStatus {
  available: boolean;
  reason: TribunalStatusReason | null;
  message: string | null;
  provider: string | null;
  model: string | null;
  key_source: 'user' | 'server' | null;
  limit: { daily_limit: number; used_today: number; remaining: number; resets_at: string } | null;
  scope: TribunalScope;
}

export interface TribunalLatestResponse {
  session: TribunalSession | null;
  current_case_file_hash: string | null;
  data_changed: boolean | null;
}

export interface TribunalStreamError {
  code: TribunalStreamErrorCode;
  message: string;
  retryable: boolean;
  phase: TribunalPhase | null;
}

export interface TribunalDone {
  session_id: string;
  reused: boolean;
  saved: boolean;
  duration_ms: number;
  totals: TribunalTotals;
}

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

export type TribunalEventType = TribunalEvent['type'];
