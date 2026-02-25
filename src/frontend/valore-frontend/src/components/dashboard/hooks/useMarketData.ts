import { useState } from 'react';
import { getMarketQuotes } from '../../../services/api';
import type { MarketQuotesResponse } from '../../../services/api';

export interface MarketDataState {
  data: MarketQuotesResponse | null;
  loading: boolean;
  error: string | null;
  loaded: boolean;
  lastUpdatedAt: string | null;
  fetchMarketData: (force?: boolean) => Promise<void>;
}

export function useMarketData(): MarketDataState {
  const [data, setData] = useState<MarketQuotesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const fetchMarketData = async (force = false) => {
    if (loading) return;
    if (loaded && !force) return;

    setLoading(true);
    setError(null);
    try {
      const response = await getMarketQuotes();
      setData(response);
      setLoaded(true);
      setLastUpdatedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore caricamento mercati');
    } finally {
      setLoading(false);
    }
  };

  return { data, loading, error, loaded, lastUpdatedAt, fetchMarketData };
}
