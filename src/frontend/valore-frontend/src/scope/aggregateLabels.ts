// Italian copy shared by the pages in the aggregate (multi-portfolio) view.

/** Tooltip on write actions disabled in the aggregate view. */
export const AGGREGATE_READ_ONLY_HINT = 'Seleziona un solo portafoglio per modificare';

/** Short notice for sections that exist only for a single portfolio. */
export const AGGREGATE_UNAVAILABLE = 'Non disponibile nella vista aggregata';

/** What the aggregate view is, shown on the "Aggregato (N)" badge. */
export const AGGREGATE_READ_ONLY_EXPLANATION =
  'Vista aggregata in sola lettura: i portafogli selezionati sono letti come uno solo (posizioni sommate, '
  + 'performance sui flussi combinati). Transazioni, liquidità, PAC e target si modificano selezionando un solo portafoglio.';

/** Shown in the switcher when the user has a single portfolio. */
export const AGGREGATE_NEEDS_TWO = 'La vista aggregata unisce almeno 2 portafogli con la stessa valuta base: crea un altro portafoglio per usarla.';

/** Shown in the switcher when no other portfolio shares the current base currency. */
export const aggregateNoSameCurrency = (currency: string) =>
  `Nessun altro portafoglio in ${currency}: la vista aggregata unisce solo portafogli con la stessa valuta base.`;

/** Friendly messages for the aggregate scope errors of the API. */
export const AGGREGATE_ERROR_MIXED_CURRENCY =
  'I portafogli selezionati hanno valute base diverse: la vista aggregata unisce solo portafogli nella stessa valuta.';
export const AGGREGATE_ERROR_NOT_FOUND =
  'Uno dei portafogli della vista aggregata non esiste più (forse è stato eliminato in un\'altra scheda): la selezione è stata aggiornata.';
export const AGGREGATE_ERROR_EMPTY = 'Seleziona almeno un portafoglio.';
export const AGGREGATE_ERROR_TOO_MANY = 'Puoi aggregare al massimo 20 portafogli.';
export const AGGREGATE_EMPTY_POSITIONS = 'Nessuna posizione nei portafogli selezionati.';
