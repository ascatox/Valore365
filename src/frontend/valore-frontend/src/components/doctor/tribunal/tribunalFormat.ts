// Tribunale del portafoglio — etichette, colori e testi dell'interfaccia
// (docs/tribunale/ui-spec.md §4.1, §5, §6, §8, §11). Solo formattazione: i valori dei
// fatti arrivano già formattati dal backend (`formatted`) e non vengono mai ricalcolati.
import {
  IconAlertTriangle,
  IconArrowsExchange,
  IconCircleCheck,
  IconCircleDot,
  IconInfoCircle,
  IconThumbUp,
  type Icon,
} from '@tabler/icons-react';
import type {
  TribunalDiscardCode,
  TribunalFact,
  TribunalFactGroup,
  TribunalFactQuality,
  TribunalFactSource,
  TribunalPhase,
  TribunalRebuttalStance,
  TribunalStance,
  TribunalTheme,
  TribunalVoiceError,
  TribunalVoiceId,
  TribunalVoiceInfo,
} from '../../../services/api/tribunalTypes';
import { maskMoneyInText, PRIVACY_MASK } from '../policy/policyFormat';

export { PRIVACY_MASK };

// ---------------------------------------------------------------- voci (§6.1, §11)

export interface TribunalVoiceMeta {
  id: TribunalVoiceId;
  code: 'IND' | 'FAT' | 'PRU';
  name: string;
  /** Etichetta della scheda su mobile. */
  tabLabel: string;
  /** Colore Mantine (mai `teal`, riservato alla marca). */
  color: 'blue' | 'grape' | 'orange';
  /** Testo esatto di `VoiceInfo.mandate` (contratto §5.1), usato finché il backend non risponde. */
  mandate: string;
  /** Articolo determinativo del nome, per le preposizioni articolate («del», «dell'»). */
  article: 'il' | "l'";
  /** Nome senza articolo, in minuscolo («fattoriale»). */
  noun: string;
}

export const TRIBUNAL_VOICES: readonly TribunalVoiceMeta[] = [
  { id: 'indicizzatore', code: 'IND', name: "L'indicizzatore", tabLabel: 'Indicizzatore', color: 'blue', mandate: 'Basso costo, ampia diversificazione, semplicità.', article: "l'", noun: 'indicizzatore' },
  { id: 'fattoriale', code: 'FAT', name: 'Il fattoriale', tabLabel: 'Fattoriale', color: 'grape', mandate: 'Inclinazioni volute, concentrazione consapevole.', article: 'il', noun: 'fattoriale' },
  { id: 'prudente', code: 'PRU', name: 'Il prudente', tabLabel: 'Prudente', color: 'orange', mandate: 'Protezione del capitale, reddito, tenuta nei ribassi.', article: 'il', noun: 'prudente' },
];

const VOICE_BY_ID = new Map(TRIBUNAL_VOICES.map((voice) => [voice.id, voice]));
const VOICE_BY_CODE = new Map(TRIBUNAL_VOICES.map((voice) => [voice.code, voice]));

export function voiceMeta(id: TribunalVoiceId): TribunalVoiceMeta {
  return VOICE_BY_ID.get(id) ?? TRIBUNAL_VOICES[0];
}

/** Voci da mostrare, sempre nell'ordine canonico, con nome e mandato del backend se presenti. */
export function resolveVoices(voices: TribunalVoiceInfo[] | null | undefined): TribunalVoiceInfo[] {
  return TRIBUNAL_VOICES.map((meta) => {
    const fromBackend = voices?.find((voice) => voice.id === meta.id);
    return fromBackend ?? { id: meta.id, code: meta.code, name: meta.name, mandate: meta.mandate };
  });
}

export function voiceName(id: TribunalVoiceId, voices?: TribunalVoiceInfo[] | null): string {
  return voices?.find((voice) => voice.id === id)?.name ?? voiceMeta(id).name;
}

export type ItalianPreposition = 'di' | 'a' | 'da' | 'in' | 'su' | 'con' | 'per' | 'tra';

/** Preposizioni articolate con «il» e «l'»; con, per, tra restano separate dall'articolo. */
const ARTICULATED: Record<ItalianPreposition, Record<TribunalVoiceMeta['article'], string>> = {
  di: { il: 'del ', "l'": "dell'" },
  a: { il: 'al ', "l'": "all'" },
  da: { il: 'dal ', "l'": "dall'" },
  in: { il: 'nel ', "l'": "nell'" },
  su: { il: 'sul ', "l'": "sull'" },
  con: { il: 'con il ', "l'": "con l'" },
  per: { il: 'per il ', "l'": "per l'" },
  tra: { il: 'tra il ', "l'": "tra l'" },
};

/**
 * Nome della voce dopo una preposizione, a partire dall'id: «del fattoriale», «dell'indicizzatore»,
 * «al prudente», «con l'indicizzatore». Usa sempre il nome canonico in minuscolo.
 */
export function voiceWithPreposition(preposition: ItalianPreposition, id: TribunalVoiceId): string {
  const meta = voiceMeta(id);
  return `${ARTICULATED[preposition][meta.article]}${meta.noun}`;
}

/** `var(--mantine-color-<colore>-6)`: token del tema, uguale in chiaro e in scuro. */
export const voiceColorVar = (id: TribunalVoiceId) => `var(--mantine-color-${voiceMeta(id).color}-6)`;

/** Voce a cui appartiene un argomento (`A-IND-1`) o una replica (`R-FAT-2`) dal suo id. */
export function voiceOfElementId(id: string): TribunalVoiceId | null {
  const match = /^[AR]-(IND|FAT|PRU)-\d+$/.exec(id);
  if (!match) return null;
  return VOICE_BY_CODE.get(match[1] as TribunalVoiceMeta['code'])?.id ?? null;
}

/** Id DOM di una card (argomento, replica): `tribunal-<id elemento>`. */
export const elementDomId = (id: string) => `tribunal-${id}`;

// ---------------------------------------------------------------- posizioni (§6.2)

export interface StanceMeta {
  label: string;
  icon: Icon;
  color: string;
  variant: 'light' | 'outline';
}

export const STANCE_META: Record<TribunalStance, StanceMeta> = {
  punto_di_forza: { label: 'Punto di forza', icon: IconCircleCheck, color: 'green', variant: 'light' },
  criticita: { label: 'Criticità', icon: IconAlertTriangle, color: 'red', variant: 'light' },
  neutro: { label: 'Osservazione', icon: IconCircleDot, color: 'gray', variant: 'light' },
};

export const REBUTTAL_STANCE_META: Record<TribunalRebuttalStance, StanceMeta> = {
  concorda: { label: 'Concorda', icon: IconThumbUp, color: 'gray', variant: 'outline' },
  contesta: { label: 'Contesta', icon: IconArrowsExchange, color: 'gray', variant: 'outline' },
  precisa: { label: 'Precisa', icon: IconInfoCircle, color: 'gray', variant: 'outline' },
};

// ---------------------------------------------------------------- temi, qualità, fonti (§6.3–6.5)

export const THEME_LABELS: Record<TribunalTheme, string> = {
  costi: 'Costi',
  diversificazione: 'Diversificazione',
  concentrazione: 'Concentrazione',
  composizione: 'Composizione',
  esposizione_geografica: 'Esposizione geografica',
  esposizione_settoriale: 'Esposizione settoriale',
  rischio: 'Rischio',
  scenari: 'Scenari',
  regole_personali: 'I miei parametri',
  qualita_dati: 'Qualità dei dati',
};

export const themeLabel = (theme: string) => THEME_LABELS[theme as TribunalTheme] ?? theme;

export interface QualityMeta {
  label: string;
  color: string;
}

export const QUALITY_META: Record<TribunalFactQuality, QualityMeta> = {
  ok: { label: 'Dato completo', color: 'green' },
  partial: { label: 'Dato parziale', color: 'yellow' },
  stale: { label: 'Quotazioni non aggiornate', color: 'yellow' },
  missing: { label: 'Dato mancante', color: 'gray' },
};

export const qualityMeta = (quality: string): QualityMeta => QUALITY_META[quality as TribunalFactQuality] ?? QUALITY_META.missing;

export const SOURCE_LABELS: Record<TribunalFactSource, string> = {
  doctor_metrics: 'Metriche del Doctor',
  positions: 'Posizioni del portafoglio',
  health_score: 'Punteggio di salute',
  health_alerts: 'Avvisi del Doctor',
  xray: 'X-Ray (look-through)',
  stress_test: 'Stress test storici',
  monte_carlo: 'Simulazione Monte Carlo',
  doctor_policy: 'I miei parametri',
};

export const sourceLabel = (source: string) => SOURCE_LABELS[source as TribunalFactSource] ?? source;

/** Gruppi del fascicolo, nell'ordine del catalogo (contratto §4.3). */
export const GROUP_LABELS: Record<TribunalFactGroup, string> = {
  composizione: 'Composizione',
  concentrazione: 'Concentrazione',
  costi: 'Costi',
  salute: 'Salute del portafoglio',
  esposizione: 'Esposizione',
  stress: 'Stress test',
  scenari: 'Scenari',
  regole: 'I miei parametri',
};

// ---------------------------------------------------------------- scartati (§6.6)

export const DISCARD_CODE_LABELS: Record<TribunalDiscardCode, string> = {
  schema_non_valido: 'risposta incompleta o malformata',
  riferimento_non_ammesso: 'risposta a un argomento non valido',
  nessun_fatto: 'nessun dato del Doctor citato',
  troppi_fatti: 'troppi dati citati insieme',
  fatto_inesistente: 'dato citato che non esiste',
  fatto_non_citabile: 'dato mancante o non aggiornato',
  segnaposto_malformato: 'riferimento a un dato scritto male',
  segnaposto_non_citato: 'valore non dichiarato tra le fonti',
  fatto_estraneo: 'dato non usato dalle voci richiamate',
  testo_troppo_lungo: 'testo troppo lungo',
  strumento_non_ammesso: 'strumento non presente nel portafoglio',
  cifra_libera: 'numero scritto senza prenderlo dai dati',
  indicazione_operativa: 'indicazione di acquisto, vendita o consiglio',
  verdetto: 'giudizio su chi ha ragione',
  troppi_argomenti: 'oltre il numero massimo di argomenti',
};

export const discardCodeLabel = (code: string) => DISCARD_CODE_LABELS[code as TribunalDiscardCode] ?? code;

export function discardedTitle(total: number): string {
  return total === 1
    ? '1 affermazione scartata dal controllo automatico'
    : `${total} affermazioni scartate dal controllo automatico`;
}

export const DISCARDED_EXPLANATION = 'Prima di mostrarti una frase, il Tribunale controlla che ogni numero venga dai '
  + 'dati del Doctor, che non nomini strumenti fuori dal tuo portafoglio e che non contenga indicazioni di acquisto '
  + 'o vendita. Le frasi che non superano il controllo non vengono mostrate: qui vedi solo quante sono e perché.';

// ---------------------------------------------------------------- avvertenza (§5)

export const DISCLAIMER_FIRST = 'Il Tribunale mette a confronto tre letture automatiche del tuo portafoglio, ciascuna '
  + 'con un punto di vista dichiarato.';
export const DISCLAIMER_MIDDLE = 'Ogni numero viene dai calcoli del Doctor; i testi sono generati da un modello di '
  + 'intelligenza artificiale e possono essere incompleti. Non è una consulenza finanziaria personalizzata: non indica '
  + 'cosa comprare o vendere e non valuta se il portafoglio è adatto a te.';
export const DISCLAIMER_LAST = 'Le scelte restano tue.';
export const DISCLAIMER_TEXT = `${DISCLAIMER_FIRST} ${DISCLAIMER_MIDDLE} ${DISCLAIMER_LAST}`;

// ---------------------------------------------------------------- fasi (§3, §10)

export const PHASE_STEPS = ['Fascicolo', 'Apertura', 'Replica', 'Sintesi'] as const;

/** Indice del passo in corso dello Stepper (4 = tutti completati). */
export function phaseStepIndex(
  phase: TribunalPhase | null,
  hasCaseFile: boolean,
  completed: boolean,
  completedPhases: readonly TribunalPhase[] = [],
): number {
  if (completed) return PHASE_STEPS.length;
  if (phase && completedPhases.includes(phase)) {
    return Math.min(PHASE_STEPS.length, phaseStepIndex(phase, hasCaseFile, false) + 1);
  }
  if (phase === 'sintesi') return 3;
  if (phase === 'replica') return 2;
  if (phase === 'apertura' || hasCaseFile) return 1;
  return 0;
}

// ---------------------------------------------------------------- messaggi (§4.1)

const COPILOT_NOT_CONFIGURED = 'Il Tribunale usa il Copilot, che non è ancora configurato. Aggiungi una chiave API in '
  + 'Impostazioni → Copilot.';

const ERROR_MESSAGES: Record<string, string> = {
  copilot_not_configured: COPILOT_NOT_CONFIGURED,
  copilot_unavailable: COPILOT_NOT_CONFIGURED,
  provider_not_supported: 'Il modello configurato non supporta le risposte strutturate richieste dal Tribunale. In '
    + 'Impostazioni → Copilot scegli OpenAI, Anthropic, Gemini oppure OpenRouter.',
  session_in_progress: "C'è già una seduta in corso. Attendi che finisca prima di avviarne un'altra.",
  empty_portfolio: 'Il portafoglio non ha posizioni investite: non c\'è ancora nulla da discutere.',
  insufficient_data: 'Il Doctor non ha abbastanza dati affidabili per una seduta. Aggiorna le quotazioni o completa i '
    + 'dati degli strumenti e riprova.',
  not_found: 'Portafoglio non trovato.',
  invalid_request: 'Selezione dei portafogli non valida.',
  timeout: 'La seduta ha impiegato troppo tempo ed è stata interrotta.',
  too_few_voices: 'Meno di due voci hanno prodotto argomenti verificabili: la seduta si è fermata. Riprova tra poco.',
  synthesis_failed: 'La sintesi non è riuscita. Gli argomenti delle voci restano visibili.',
  internal_error: 'Errore imprevisto durante la seduta.',
  stream_interrupted: 'La connessione si è interrotta prima della fine della seduta.',
  network_error: 'Connessione interrotta prima della risposta. Controlla la rete e riprova.',
};

/** «HH:MM» in ora locale. */
export function formatLocalTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

/** «10 novembre 2026, 15:03» in ora locale (§6.7). */
export function formatSessionDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const day = date.toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' });
  return `${day}, ${formatLocalTime(iso)}`;
}

export function dailyLimitMessage(resetsAt: string | null | undefined): string {
  const time = formatLocalTime(resetsAt);
  const when = time ? `dalle ${time}` : 'da domani';
  return `Hai usato tutte le sedute di oggi disponibili con la chiave del server. Potrai avviarne un'altra ${when}. `
    + 'Con una tua chiave API, in Impostazioni → Copilot, non ci sono limiti giornalieri.';
}

/**
 * Testo per un codice di errore o di stato (§4.1); il `message` del backend serve solo per
 * codici sconosciuti e passa dalla maschera degli importi.
 */
export function tribunalMessage(
  code: string | null | undefined,
  fallback: string | null | undefined,
  options: { privacy?: boolean; resetsAt?: string | null } = {},
): string {
  if (code === 'daily_limit_reached') return dailyLimitMessage(options.resetsAt);
  const known = code ? ERROR_MESSAGES[code] : undefined;
  if (known) return known;
  const text = fallback?.trim() ? fallback.trim() : ERROR_MESSAGES.internal_error;
  return maskMoneyInText(text, options.privacy ?? false);
}

export function voiceErrorMessage(error: Pick<TribunalVoiceError, 'code' | 'message'>, name: string, privacy = false): string {
  switch (error.code) {
    case 'timeout':
      return `${name} non ha risposto in tempo: la seduta prosegue con le altre voci.`;
    case 'schema_mismatch':
      return `${name} ha risposto in un formato non valido: la seduta prosegue con le altre voci.`;
    case 'provider_error':
    case 'unsupported_provider':
      return `${name} non è disponibile per un errore del servizio AI: la seduta prosegue con le altre voci.`;
    default:
      return maskMoneyInText(error.message || `${name} non ha risposto: la seduta prosegue con le altre voci.`, privacy);
  }
}

// ---------------------------------------------------------------- testo con fatti (§3.1, §8)

export type TemplatePart = { kind: 'text'; value: string } | { kind: 'fact'; id: string };

const PLACEHOLDER = /\{F([1-9][0-9]{0,2})\}/g;

/** Divide un `text_template` in testo semplice e segnaposto `{Fn}`. */
export function splitTemplate(template: string | null | undefined): TemplatePart[] {
  if (!template) return [];
  const parts: TemplatePart[] = [];
  let last = 0;
  for (const match of template.matchAll(PLACEHOLDER)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ kind: 'text', value: template.slice(last, index) });
    parts.push({ kind: 'fact', id: `F${match[1]}` });
    last = index + match[0].length;
  }
  if (last < template.length) parts.push({ kind: 'text', value: template.slice(last) });
  return parts;
}

/** Valore mostrato di un fatto: `formatted` così com'è, o la maschera se sensibile in Privacy Mode. */
export function factDisplayValue(fact: Pick<TribunalFact, 'formatted' | 'sensitive'>, privacy: boolean): string {
  return privacy && fact.sensitive ? PRIVACY_MASK : fact.formatted;
}

export function factAriaLabel(fact: Pick<TribunalFact, 'id' | 'label' | 'formatted' | 'sensitive'>, privacy: boolean): string {
  const value = privacy && fact.sensitive ? 'nascosto' : fact.formatted;
  return `Dato ${fact.id}: ${maskMoneyInText(fact.label, privacy)}, ${value}. Apri i dettagli`;
}

export { maskMoneyInText };
