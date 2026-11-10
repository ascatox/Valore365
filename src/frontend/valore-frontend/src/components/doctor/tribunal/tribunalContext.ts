// Contesto condiviso dai componenti della seduta: fatti del fascicolo, Privacy Mode, resa
// compatta (< 62em) e navigazione verso una card (scroll e focus, cambio scheda su mobile).
import { createContext, useContext } from 'react';
import type { TribunalFact, TribunalVoiceInfo } from '../../../services/api/tribunalTypes';

export interface TribunalViewContextValue {
  facts: ReadonlyMap<string, TribunalFact>;
  voices: TribunalVoiceInfo[];
  privacy: boolean;
  compact: boolean;
  /** Porta il focus sulla card `tribunal-<id>` (argomento o replica). */
  goTo: (elementId: string) => void;
}

const EMPTY_FACTS: ReadonlyMap<string, TribunalFact> = new Map();

export const TribunalViewContext = createContext<TribunalViewContextValue>({
  facts: EMPTY_FACTS,
  voices: [],
  privacy: false,
  compact: false,
  goTo: () => undefined,
});

export const useTribunalView = () => useContext(TribunalViewContext);
