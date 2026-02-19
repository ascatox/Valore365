import type {
  AssetCreateRequest,
  AssetProviderSymbolCreateRequest,
  AssetRead,
  AssetSearchItem,
  DailyBackfillResponse,
  PortfolioSummary,
  Position,
  PriceRefreshResponse,
  TimeSeriesPoint,
  TransactionCreateRequest,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function buildHeaders(token?: string): HeadersInit {
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

async function requestJson<T>(path: string, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: buildHeaders(token),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<TResponse, TBody>(path: string, body: TBody, token?: string): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<TResponse>;
}

export async function getSummary(portfolioId: number, token?: string): Promise<PortfolioSummary> {
  return requestJson<PortfolioSummary>(`/portfolios/${portfolioId}/summary`, token);
}

export async function getPositions(portfolioId: number, token?: string): Promise<Position[]> {
  return requestJson<Position[]>(`/portfolios/${portfolioId}/positions`, token);
}

export async function getTimeSeries(portfolioId: number, token?: string): Promise<TimeSeriesPoint[]> {
  return requestJson<TimeSeriesPoint[]>(`/portfolios/${portfolioId}/timeseries?range=1y&interval=1d`, token);
}

export async function createAsset(payload: AssetCreateRequest, token?: string): Promise<AssetRead> {
  return postJson<AssetRead, AssetCreateRequest>("/assets", payload, token);
}

export async function createAssetProviderSymbol(
  payload: AssetProviderSymbolCreateRequest,
  token?: string
): Promise<AssetProviderSymbolCreateRequest> {
  return postJson<AssetProviderSymbolCreateRequest, AssetProviderSymbolCreateRequest>("/asset-provider-symbols", payload, token);
}

export async function createTransaction(payload: TransactionCreateRequest, token?: string): Promise<unknown> {
  return postJson<unknown, TransactionCreateRequest>("/transactions", payload, token);
}

export async function searchAssets(query: string, token?: string): Promise<AssetSearchItem[]> {
  const result = await requestJson<{ items: AssetSearchItem[] }>(`/assets/search?q=${encodeURIComponent(query)}`, token);
  return result.items;
}

export async function refreshPrices(portfolioId: number, token?: string): Promise<PriceRefreshResponse> {
  return postJson<PriceRefreshResponse, Record<string, never>>(`/prices/refresh?portfolio_id=${portfolioId}`, {}, token);
}

export async function backfillDaily(portfolioId: number, days = 365, token?: string): Promise<DailyBackfillResponse> {
  return postJson<DailyBackfillResponse, Record<string, never>>(
    `/prices/backfill-daily?portfolio_id=${portfolioId}&days=${days}`,
    {},
    token
  );
}
