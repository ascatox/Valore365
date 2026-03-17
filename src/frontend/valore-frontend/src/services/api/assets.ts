import { apiFetch, ApiRequestError } from './client';
import type {
  Symbol,
  AssetSearchResult,
  AssetDiscoverItem,
  AssetCreateInput,
  AssetRead,
  AssetProviderSymbolCreateInput,
  AssetEnsureInput,
  AssetEnsureResponse,
  AssetLatestQuoteResponse,
  AssetInfo,
  AssetPricePoint,
  EtfEnrichment,
} from './types';

export const getSymbols = async (query: string): Promise<Symbol[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ symbols: Symbol[] }>(`/symbols?q=${encodeURIComponent(q)}`);
  return payload.symbols ?? [];
};

export const searchAssets = async (query: string): Promise<AssetSearchResult[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ assets: AssetSearchResult[] }>(`/assets/search?q=${encodeURIComponent(q)}`);
  return payload.assets ?? [];
};

export const discoverAssets = async (query: string): Promise<AssetDiscoverItem[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ items: AssetDiscoverItem[] }>(`/assets/discover?q=${encodeURIComponent(q)}`);
  return payload.items ?? [];
};

export const createAsset = async (payload: AssetCreateInput): Promise<AssetRead> => {
  return apiFetch<AssetRead>('/assets', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const createAssetProviderSymbol = async (payload: AssetProviderSymbolCreateInput): Promise<AssetProviderSymbolCreateInput> => {
  return apiFetch<AssetProviderSymbolCreateInput>('/asset-provider-symbols', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const ensureAsset = async (payload: AssetEnsureInput): Promise<AssetEnsureResponse> => {
  return apiFetch<AssetEnsureResponse>('/assets/ensure', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getAssetLatestQuote = async (assetId: number): Promise<AssetLatestQuoteResponse> => {
  return apiFetch<AssetLatestQuoteResponse>(`/assets/${assetId}/latest-quote`);
};

export const getAssetInfo = async (assetId: number): Promise<AssetInfo> => {
  return apiFetch<AssetInfo>(`/assets/${assetId}/info`);
};

export const getAssetPriceTimeseries = async (
  assetId: number,
  startDate?: string,
  endDate?: string,
): Promise<AssetPricePoint[]> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<AssetPricePoint[]>(
    `/assets/${assetId}/price-timeseries${query ? `?${query}` : ''}`,
  );
};

export const getEtfEnrichment = async (assetId: number): Promise<EtfEnrichment | null> => {
  try {
    return await apiFetch<EtfEnrichment>(`/assets/${assetId}/etf-enrichment`);
  } catch (err) {
    if (err instanceof ApiRequestError && err.status === 404) return null;
    throw err;
  }
};

export const refreshEtfEnrichment = async (assetId: number): Promise<EtfEnrichment> => {
  return apiFetch<EtfEnrichment>(`/assets/${assetId}/etf-enrichment/refresh`, { method: 'POST' });
};
