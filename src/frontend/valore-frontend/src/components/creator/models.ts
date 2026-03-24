import type { PortfolioModel, PortfolioModelRecommendation, ProfileAnswers, RiskLevel } from './types';

/**
 * Palette colori per le asset class — coerente con i chart del dashboard.
 */
const C = {
  equity:      '#339af0', // blu
  equityUs:    '#228be6',
  equityEu:    '#5c7cfa',
  equityEm:    '#845ef7',
  equitySmall: '#3bc9db',
  bondLong:    '#20c997', // teal
  bondMid:     '#38d9a9',
  bondShort:   '#69db7c', // verde
  bondGlobal:  '#51cf66',
  bondEur:     '#94d82d', // lime
  btp:         '#a9e34b',
  gold:        '#fcc419', // giallo
  commodity:   '#ff922b', // arancione
} as const;

export const PORTFOLIO_MODELS: PortfolioModel[] = [
  /* ------------------------------------------------------------------ */
  {
    id: 'all-weather',
    name: 'All Weather',
    subtitle: 'Ray Dalio',
    description:
      'Progettato per funzionare in ogni fase economica: crescita, recessione, inflazione e deflazione. Bassa volatilita\' e rendimenti stabili.',
    risk: 'low',
    tags: ['classico', 'difensivo', 'all-season'],
    slots: [
      { label: 'Azioni USA',            weight: 30, color: C.equityUs,  ticker: 'VTI',  isin: 'IE00B3XXRP09' },
      { label: 'Obbligazioni lungo',    weight: 40, color: C.bondLong,  ticker: 'TLT',  isin: 'IE00B1FZS798' },
      { label: 'Obbligazioni medio',    weight: 15, color: C.bondMid,   ticker: 'IEF',  isin: 'IE00B3FH7618' },
      { label: 'Oro',                   weight: 7.5, color: C.gold,     ticker: 'GLD',  isin: 'IE00B4ND3602' },
      { label: 'Commodity',             weight: 7.5, color: C.commodity, ticker: 'DJP',  isin: 'IE00BDFL4P12' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'golden-butterfly',
    name: 'Golden Butterfly',
    subtitle: 'Tyler (Portfolio Charts)',
    description:
      'Bilancia crescita e protezione in cinque fette uguali. Small-cap value per la crescita, oro e obbligazioni per la difesa.',
    risk: 'medium-low',
    tags: ['bilanciato', 'difensivo', 'small-cap'],
    slots: [
      { label: 'Azioni large cap',       weight: 20, color: C.equity,      ticker: 'VTI',   isin: 'IE00B3XXRP09' },
      { label: 'Azioni small cap value', weight: 20, color: C.equitySmall, ticker: 'VBR',   isin: 'IE00BSPLC298' },
      { label: 'Obbligazioni lungo',     weight: 20, color: C.bondLong,    ticker: 'TLT',   isin: 'IE00B1FZS798' },
      { label: 'Obbligazioni breve',     weight: 20, color: C.bondShort,   ticker: 'SHY',   isin: 'IE00B3FH7618' },
      { label: 'Oro',                    weight: 20, color: C.gold,        ticker: 'GLD',   isin: 'IE00B4ND3602' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'classic-60-40',
    name: 'Classic 60/40',
    subtitle: 'Allocazione tradizionale',
    description:
      'Il portafoglio bilanciato per eccellenza: 60 % azioni globali per la crescita, 40 % obbligazioni aggregate per la stabilita\'.',
    risk: 'medium',
    tags: ['classico', 'bilanciato', 'semplice'],
    slots: [
      { label: 'Azioni globali',          weight: 60, color: C.equity,     ticker: 'VWCE', isin: 'IE00BK5BQT80' },
      { label: 'Obbligazioni aggregate',  weight: 40, color: C.bondGlobal, ticker: 'AGGH', isin: 'IE00BDBRDM35' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'aggressive-80-20',
    name: 'Aggressivo 80/20',
    subtitle: 'Crescita con cuscinetto',
    description:
      'Per chi ha un orizzonte lungo (15+ anni) e tollera oscillazioni importanti. 80 % azionario diversificato, 20 % obbligazionario.',
    risk: 'high',
    tags: ['crescita', 'lungo termine', 'aggressivo'],
    slots: [
      { label: 'Azioni USA',          weight: 50, color: C.equityUs, ticker: 'VTI',  isin: 'IE00B3XXRP09' },
      { label: 'Azioni Europa',       weight: 20, color: C.equityEu, ticker: 'VEUR', isin: 'IE00BK5BQX27' },
      { label: 'Azioni Emergenti',    weight: 10, color: C.equityEm, ticker: 'VFEM', isin: 'IE00B3VVMM84' },
      { label: 'Obbligazioni globali', weight: 20, color: C.bondGlobal, ticker: 'AGGH', isin: 'IE00BDBRDM35' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'full-equity',
    name: '100 % Azionario Globale',
    subtitle: 'Maximum growth',
    description:
      'Tutto in azioni: massima esposizione alla crescita di lungo periodo. Solo per chi regge drawdown del 40-50 % senza panico.',
    risk: 'very-high',
    tags: ['crescita', 'aggressivo', 'semplice'],
    slots: [
      { label: 'Azioni USA',       weight: 60, color: C.equityUs, ticker: 'VTI',  isin: 'IE00B3XXRP09' },
      { label: 'Azioni Europa',    weight: 25, color: C.equityEu, ticker: 'VEUR', isin: 'IE00BK5BQX27' },
      { label: 'Azioni Emergenti', weight: 15, color: C.equityEm, ticker: 'VFEM', isin: 'IE00B3VVMM84' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'pigro-italiano',
    name: 'Pigro Italiano',
    subtitle: 'Ottimizzato per l\'investitore IT',
    description:
      'Bilanciato con componente BTP/obbligazionaria EUR per efficienza fiscale italiana e protezione dall\'inflazione locale.',
    risk: 'medium',
    tags: ['bilanciato', 'italia', 'fiscalmente efficiente'],
    slots: [
      { label: 'Azioni globali',      weight: 40, color: C.equity,   ticker: 'VWCE', isin: 'IE00BK5BQT80' },
      { label: 'BTP / Obblig. EUR',   weight: 30, color: C.btp,      ticker: 'XGLE', isin: 'LU0290355717' },
      { label: 'Obbligazioni globali', weight: 20, color: C.bondGlobal, ticker: 'AGGH', isin: 'IE00BDBRDM35' },
      { label: 'Oro',                 weight: 10, color: C.gold,     ticker: 'SGLD', isin: 'IE00B4ND3602' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'permanent-portfolio',
    name: 'Permanent Portfolio',
    subtitle: 'Harry Browne',
    description:
      'Quattro asset class in parti uguali: azioni, obbligazioni lungo, oro e liquidita\'. Pensato per sopravvivere a qualsiasi scenario.',
    risk: 'low',
    tags: ['classico', 'difensivo', 'semplice'],
    slots: [
      { label: 'Azioni USA',           weight: 25, color: C.equityUs, ticker: 'VTI',  isin: 'IE00B3XXRP09' },
      { label: 'Obbligazioni lungo',   weight: 25, color: C.bondLong, ticker: 'TLT',  isin: 'IE00B1FZS798' },
      { label: 'Oro',                  weight: 25, color: C.gold,     ticker: 'GLD',  isin: 'IE00B4ND3602' },
      { label: 'Liquidita\' / breve',  weight: 25, color: C.bondShort, ticker: 'SHY', isin: 'IE00B3FH7618' },
    ],
  },

  /* ------------------------------------------------------------------ */
  {
    id: 'three-fund',
    name: 'Three-Fund Portfolio',
    subtitle: 'Bogleheads',
    description:
      'Il preferito della community Bogleheads: azioni USA, azioni internazionali e obbligazioni. Semplicita\' massima, costi minimi.',
    risk: 'medium',
    tags: ['classico', 'semplice', 'bogleheads'],
    slots: [
      { label: 'Azioni USA',             weight: 40, color: C.equityUs,    ticker: 'VTI',  isin: 'IE00B3XXRP09' },
      { label: 'Azioni internazionali',  weight: 20, color: C.equityEu,    ticker: 'VXUS', isin: 'IE00BK5BQX27' },
      { label: 'Obbligazioni aggregate', weight: 40, color: C.bondGlobal,  ticker: 'AGGH', isin: 'IE00BDBRDM35' },
    ],
  },
];

/** Mappa rischio → label italiano e colore Mantine */
export const RISK_META: Record<string, { label: string; color: string; bars: number }> = {
  'low':        { label: 'Basso',       color: 'green',  bars: 1 },
  'medium-low': { label: 'Medio-basso', color: 'teal',   bars: 2 },
  'medium':     { label: 'Medio',       color: 'yellow', bars: 3 },
  'high':       { label: 'Alto',        color: 'orange', bars: 4 },
  'very-high':  { label: 'Molto alto',  color: 'red',    bars: 5 },
};

const RISK_SCORE: Record<RiskLevel, number> = {
  low: 1,
  'medium-low': 2,
  medium: 3,
  high: 4,
  'very-high': 5,
};

const HORIZON_SCORE: Record<ProfileAnswers['horizon'], number> = {
  lt5: 1,
  '5to10': 2,
  '10to20': 4,
  gt20: 5,
};

const TOLERANCE_SCORE: Record<ProfileAnswers['riskTolerance'], number> = {
  sell_all: 1,
  sell_some: 2,
  hold: 4,
  buy_more: 5,
};

const OBJECTIVE_SCORE: Record<ProfileAnswers['objective'], number> = {
  capital_preservation: 1,
  income: 2,
  moderate_growth: 3,
  max_growth: 5,
};

function getTargetRiskScore(answers: ProfileAnswers): number {
  const weightedScore = (
    HORIZON_SCORE[answers.horizon] * 0.3
    + TOLERANCE_SCORE[answers.riskTolerance] * 0.45
    + OBJECTIVE_SCORE[answers.objective] * 0.25
  );

  return Math.max(1, Math.min(5, Math.round(weightedScore)));
}

function getObjectiveBonus(model: PortfolioModel, objective: ProfileAnswers['objective']): number {
  if (objective === 'capital_preservation') {
    return model.tags.includes('difensivo') ? 10 : 0;
  }
  if (objective === 'moderate_growth') {
    return model.tags.includes('bilanciato') || model.tags.includes('semplice') ? 8 : 0;
  }
  if (objective === 'max_growth') {
    return model.tags.includes('crescita') || model.tags.includes('aggressivo') ? 12 : 0;
  }
  return model.tags.includes('difensivo') || model.tags.includes('bilanciato') ? 8 : 0;
}

function getHorizonBonus(model: PortfolioModel, horizon: ProfileAnswers['horizon']): number {
  if (horizon === 'lt5') {
    return RISK_SCORE[model.risk] <= 2 ? 8 : 0;
  }
  if (horizon === '5to10') {
    return RISK_SCORE[model.risk] <= 3 ? 6 : 0;
  }
  if (horizon === '10to20') {
    return RISK_SCORE[model.risk] >= 3 ? 6 : 0;
  }
  return RISK_SCORE[model.risk] >= 4 ? 8 : 0;
}

function getRecommendationReason(model: PortfolioModel, answers: ProfileAnswers, targetRiskScore: number): string {
  const riskMeta = RISK_META[model.risk];
  const riskSentence = targetRiskScore <= 2
    ? `Ha un profilo ${riskMeta.label.toLowerCase()} coerente con un approccio prudente.`
    : targetRiskScore === 3
      ? `Mantiene un equilibrio credibile tra crescita e stabilita'.`
      : `Spinge di piu' sulla crescita ed e' coerente con una tolleranza al rischio elevata.`;

  const objectiveSentence = answers.objective === 'capital_preservation'
    ? 'La composizione privilegia protezione e resilienza.'
    : answers.objective === 'moderate_growth'
      ? 'La composizione cerca crescita moderata senza estremizzare la volatilita\'.'
      : answers.objective === 'income'
        ? 'La presenza obbligazionaria aiuta a contenere gli sbalzi e sostenere un profilo da rendita.'
        : 'La componente azionaria resta centrale per il lungo periodo.';

  return `${riskSentence} ${objectiveSentence}`;
}

export function recommendPortfolioModels(
  answers: ProfileAnswers,
  limit = 2,
): PortfolioModelRecommendation[] {
  const targetRiskScore = getTargetRiskScore(answers);

  return PORTFOLIO_MODELS
    .map((model) => {
      const riskDistance = Math.abs(RISK_SCORE[model.risk] - targetRiskScore);
      const riskScore = Math.max(0, 70 - riskDistance * 18);
      const objectiveBonus = getObjectiveBonus(model, answers.objective);
      const horizonBonus = getHorizonBonus(model, answers.horizon);
      const score = riskScore + objectiveBonus + horizonBonus;

      return {
        model,
        score,
        reason: getRecommendationReason(model, answers, targetRiskScore),
      };
    })
    .sort((left, right) => right.score - left.score)
    .slice(0, limit);
}
