export function formatPriceSourceLabel(source: string | null | undefined): string | null {
  switch (source) {
    case 'fast_info':
      return 'realtime Yahoo';
    case 'history_close':
      return 'ultima chiusura';
    case 'quote':
      return 'quotazione provider';
    case 'currentPrice':
      return 'prezzo corrente';
    case 'regularMarketPrice':
      return 'mercato regolare';
    default:
      return source ?? null;
  }
}

export function formatMetadataStatusLabel(status: string | null | undefined): string | null {
  switch (status) {
    case 'complete':
      return 'metadata completi';
    case 'partial':
      return 'metadata parziali';
    case 'missing':
      return 'metadata assenti';
    default:
      return status ?? null;
  }
}

export function formatPriceHistoryStatusLabel(status: string | null | undefined): string | null {
  if (!status || status === 'available') return 'storico disponibile';
  if (status === 'empty') return 'storico vuoto';
  if (status.startsWith('unavailable:')) return 'storico non disponibile';
  return status;
}

export function formatProviderWarning(message: string | null | undefined): string | null {
  if (!message) return null;
  const normalized = message.toLowerCase();
  if (normalized.includes('realtime quote unavailable; using last close')) {
    return "Prezzo realtime non disponibile, uso l'ultima chiusura.";
  }
  if (normalized.includes('market quote unavailable')) {
    return 'Quotazione di mercato non disponibile.';
  }
  if (normalized.includes('fast_info unavailable')) {
    return 'Feed realtime non disponibile.';
  }
  if (normalized.includes('provider down')) {
    return 'Provider temporaneamente non disponibile.';
  }
  return message;
}

export function formatXrayFailureReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  const normalized = reason.toLowerCase();
  if (normalized.includes('returned no top holdings')) {
    return 'Il provider non ha restituito le posizioni sottostanti.';
  }
  if (normalized.includes('holdings fetch failed')) {
    return 'Errore nel recupero delle posizioni sottostanti.';
  }
  if (normalized.includes('justetf enrichment missing and yfinance fallback unavailable')) {
    return 'Nessuna copertura disponibile da justETF o yfinance.';
  }
  return reason;
}
