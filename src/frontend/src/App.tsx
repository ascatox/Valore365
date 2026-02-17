import { useCallback, useEffect, useMemo, useState, type FormEvent, type MouseEvent } from "react";
import { SignIn, SignedIn, SignedOut, UserButton, useAuth } from "@clerk/clerk-react";

import {
  backfillDaily,
  createAsset,
  createAssetProviderSymbol,
  createTransaction,
  getPositions,
  getSummary,
  getTimeSeries,
  refreshPrices,
  searchAssets,
} from "./api";
import type { AssetSearchItem, AssetType, PortfolioSummary, Position, TimeSeriesPoint } from "./types";

const defaultPortfolioId = Number(import.meta.env.VITE_DEFAULT_PORTFOLIO_ID ?? 1);
type ChartRange = "1M" | "3M" | "YTD" | "1Y";
type ToastKind = "success" | "error" | "info";

type ToastItem = {
  id: number;
  kind: ToastKind;
  message: string;
};

const chartRanges: ChartRange[] = ["1M", "3M", "YTD", "1Y"];

function formatDate(dateValue: string): string {
  const date = new Date(`${dateValue}T00:00:00`);
  return date.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function App() {
  const { getToken } = useAuth();
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [timeseries, setTimeseries] = useState<TimeSeriesPoint[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [chartRange, setChartRange] = useState<ChartRange>("1Y");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [refreshingPrices, setRefreshingPrices] = useState<boolean>(false);
  const [runningBackfill, setRunningBackfill] = useState<boolean>(false);

  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const [symbol, setSymbol] = useState<string>("");
  const [name, setName] = useState<string>("");
  const [assetType, setAssetType] = useState<AssetType>("stock");
  const [exchangeCode, setExchangeCode] = useState<string>("");
  const [exchangeName, setExchangeName] = useState<string>("");
  const [quoteCurrency, setQuoteCurrency] = useState<string>("USD");
  const [isin, setIsin] = useState<string>("");
  const [providerSymbol, setProviderSymbol] = useState<string>("");
  const [autoBuy, setAutoBuy] = useState<boolean>(true);
  const [buyQuantity, setBuyQuantity] = useState<string>("1");
  const [buyPrice, setBuyPrice] = useState<string>("0");

  const [assetSuggestions, setAssetSuggestions] = useState<AssetSearchItem[]>([]);
  const [selectedExistingAsset, setSelectedExistingAsset] = useState<AssetSearchItem | null>(null);

  const pushToast = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3500);
  }, []);

  const getAccessToken = useCallback(async (): Promise<string> => {
    const token = await getToken();
    if (!token) {
      throw new Error("Token Clerk non disponibile");
    }
    return token;
  }, [getToken]);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const token = await getAccessToken();
      const [s, p, t] = await Promise.all([
        getSummary(defaultPortfolioId, token),
        getPositions(defaultPortfolioId, token),
        getTimeSeries(defaultPortfolioId, token),
      ]);
      setSummary(s);
      setPositions(p);
      setTimeseries(t);
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Errore caricamento dashboard");
    } finally {
      setLoading(false);
    }
  }, [getAccessToken, pushToast]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    const q = symbol.trim();
    if (!q || q.length < 1 || selectedExistingAsset) {
      setAssetSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const token = await getAccessToken();
        const items = await searchAssets(q, token);
        setAssetSuggestions(items.slice(0, 6));
      } catch {
        setAssetSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [getAccessToken, symbol, selectedExistingAsset]);

  const latestPoint = useMemo(() => timeseries[timeseries.length - 1], [timeseries]);
  const firstPoint = useMemo(() => timeseries[0], [timeseries]);
  const deltaYear = useMemo(() => {
    if (!latestPoint || !firstPoint) {
      return 0;
    }
    return latestPoint.market_value - firstPoint.market_value;
  }, [latestPoint, firstPoint]);

  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat("it-IT", {
        style: "currency",
        currency: summary?.base_currency ?? "EUR",
        maximumFractionDigits: 2,
      }),
    [summary?.base_currency]
  );

  const percentFormatter = useMemo(
    () =>
      new Intl.NumberFormat("it-IT", {
        style: "percent",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    []
  );

  const filteredTimeseries = useMemo(() => {
    if (timeseries.length === 0) {
      return [];
    }
    const last = new Date(`${timeseries[timeseries.length - 1].date}T00:00:00`);
    let threshold = new Date(last);

    if (chartRange === "1M") {
      threshold.setDate(last.getDate() - 30);
    } else if (chartRange === "3M") {
      threshold.setDate(last.getDate() - 90);
    } else if (chartRange === "YTD") {
      threshold = new Date(last.getFullYear(), 0, 1);
    } else {
      threshold.setDate(last.getDate() - 365);
    }

    return timeseries.filter((point) => new Date(`${point.date}T00:00:00`) >= threshold);
  }, [timeseries, chartRange]);

  const chartModel = useMemo(() => {
    const width = 900;
    const height = 300;
    const margin = { top: 20, right: 16, bottom: 34, left: 72 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;

    if (filteredTimeseries.length < 2) {
      return {
        width,
        height,
        margin,
        plotWidth,
        plotHeight,
        path: "",
        points: [] as { x: number; y: number }[],
        yTicks: [] as { value: number; y: number }[],
        xTicks: [] as { label: string; x: number }[],
      };
    }

    const values = filteredTimeseries.map((point) => point.market_value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = Math.max(max - min, 1);

    const points = filteredTimeseries.map((point, index) => {
      const x = margin.left + (index / (filteredTimeseries.length - 1)) * plotWidth;
      const y = margin.top + plotHeight - ((point.market_value - min) / range) * plotHeight;
      return { x, y };
    });

    const path = points
      .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
      .join(" ");

    const yTicks = [max, min + range / 2, min].map((value) => ({
      value,
      y: margin.top + plotHeight - ((value - min) / range) * plotHeight,
    }));

    const firstLabel = filteredTimeseries[0].date;
    const midLabel = filteredTimeseries[Math.floor((filteredTimeseries.length - 1) / 2)].date;
    const lastLabel = filteredTimeseries[filteredTimeseries.length - 1].date;
    const xTicks = [
      { label: formatDate(firstLabel), x: margin.left },
      { label: formatDate(midLabel), x: margin.left + plotWidth / 2 },
      { label: formatDate(lastLabel), x: margin.left + plotWidth },
    ];

    return {
      width,
      height,
      margin,
      plotWidth,
      plotHeight,
      path,
      points,
      yTicks,
      xTicks,
    };
  }, [filteredTimeseries]);

  const hoverPoint = useMemo(() => {
    if (hoverIndex === null || hoverIndex < 0 || hoverIndex >= filteredTimeseries.length) {
      return null;
    }
    return {
      data: filteredTimeseries[hoverIndex],
      coord: chartModel.points[hoverIndex],
    };
  }, [hoverIndex, filteredTimeseries, chartModel.points]);

  const topAllocation = useMemo(() => {
    const total = positions.reduce((acc, position) => acc + position.market_value, 0);
    if (total <= 0) {
      return [];
    }
    return positions.slice(0, 8).map((position) => ({
      symbol: position.symbol,
      weight: (position.market_value / total) * 100,
    }));
  }, [positions]);

  const pnlToneClass = summary && summary.unrealized_pl >= 0 ? "tone-positive" : "tone-negative";
  const deltaToneClass = deltaYear >= 0 ? "tone-positive" : "tone-negative";

  function onChartHover(event: MouseEvent<SVGRectElement>) {
    if (filteredTimeseries.length < 2) {
      setHoverIndex(null);
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const plotX = (relativeX / rect.width) * chartModel.plotWidth;
    const step = chartModel.plotWidth / (filteredTimeseries.length - 1);
    const idx = Math.round(plotX / step);
    setHoverIndex(Math.max(0, Math.min(filteredTimeseries.length - 1, idx)));
  }

  function validateQuickAdd(): string | null {
    const symbolValue = symbol.trim().toUpperCase();
    const quoteCurrencyValue = quoteCurrency.trim().toUpperCase();
    const isinValue = isin.trim().toUpperCase();
    const exchangeCodeValue = exchangeCode.trim().toUpperCase();

    if (!selectedExistingAsset && !/^[A-Z0-9.\-]{1,32}$/.test(symbolValue)) {
      return "Symbol non valido (usa lettere/numeri, max 32).";
    }
    if (!/^[A-Z]{3}$/.test(quoteCurrencyValue)) {
      return "Quote CCY non valida (formato ISO a 3 lettere).";
    }
    if (isinValue && !/^[A-Z0-9]{12}$/.test(isinValue)) {
      return "ISIN non valido (12 caratteri alfanumerici).";
    }
    if (exchangeCodeValue && !/^[A-Z0-9]{1,16}$/.test(exchangeCodeValue)) {
      return "Exchange code non valido (max 16 alfanumerici).";
    }
    if (autoBuy) {
      const qty = Number(buyQuantity);
      const price = Number(buyPrice);
      if (!(qty > 0)) {
        return "Qty Buy deve essere maggiore di zero.";
      }
      if (!(price >= 0)) {
        return "Price Buy non valido.";
      }
    }
    return null;
  }

  async function handleQuickAddSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validationError = validateQuickAdd();
    if (validationError) {
      pushToast("error", validationError);
      return;
    }

    const normalizedSymbol = symbol.trim().toUpperCase();
    const normalizedQuoteCurrency = quoteCurrency.trim().toUpperCase();
    const normalizedProviderSymbol = (providerSymbol.trim() || normalizedSymbol).toUpperCase();

    setSubmitting(true);
    try {
      const token = await getAccessToken();
      let assetId: number;
      let assetLabel: string;

      if (selectedExistingAsset) {
        assetId = Number(selectedExistingAsset.id);
        assetLabel = selectedExistingAsset.symbol;
      } else {
        const asset = await createAsset({
          symbol: normalizedSymbol,
          name: name.trim() || undefined,
          asset_type: assetType,
          exchange_code: exchangeCode.trim().toUpperCase() || undefined,
          exchange_name: exchangeName.trim() || undefined,
          quote_currency: normalizedQuoteCurrency,
          isin: isin.trim().toUpperCase() || undefined,
          active: true,
        }, token);

        await createAssetProviderSymbol({
          asset_id: asset.id,
          provider: "twelvedata",
          provider_symbol: normalizedProviderSymbol,
        }, token);

        assetId = asset.id;
        assetLabel = asset.symbol;
      }

      if (autoBuy) {
        const qty = Number(buyQuantity);
        const price = Number(buyPrice);
        await createTransaction({
          portfolio_id: defaultPortfolioId,
          asset_id: assetId,
          side: "buy",
          trade_at: new Date().toISOString(),
          quantity: qty,
          price,
          fees: 0,
          taxes: 0,
          trade_currency: normalizedQuoteCurrency,
          notes: "Quick add from frontend",
        }, token);
      }

      pushToast("success", `Titolo ${assetLabel} inserito con successo.`);
      setSymbol("");
      setName("");
      setExchangeCode("");
      setExchangeName("");
      setIsin("");
      setProviderSymbol("");
      setSelectedExistingAsset(null);
      setAssetSuggestions([]);
      await loadDashboard();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Errore inserimento titolo");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRefreshPricesNow() {
    setRefreshingPrices(true);
    try {
      const token = await getAccessToken();
      const result = await refreshPrices(defaultPortfolioId, token);
      pushToast("info", `Refresh completato: ${result.refreshed_assets}/${result.requested_assets} aggiornati.`);
      if (result.failed_assets > 0) {
        pushToast("error", `Refresh con errori su ${result.failed_assets} simboli.`);
      }
      await loadDashboard();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Errore refresh prezzi");
    } finally {
      setRefreshingPrices(false);
    }
  }

  async function handleBackfillOneYear() {
    setRunningBackfill(true);
    try {
      const token = await getAccessToken();
      const result = await backfillDaily(defaultPortfolioId, 365, token);
      pushToast(
        "info",
        `Backfill 1Y completato: asset ${result.assets_refreshed}/${result.assets_requested}, FX ${result.fx_pairs_refreshed}.`
      );
      if (result.errors.length > 0) {
        pushToast("error", `Backfill con ${result.errors.length} errori.`);
      }
      await loadDashboard();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Errore backfill 1Y");
    } finally {
      setRunningBackfill(false);
    }
  }

  return (
    <>
      <SignedOut>
        <main className="auth-shell">
          <section className="auth-card">
            <h1>Valore365</h1>
            <p>Accedi per gestire portfolio, prezzi e storico.</p>
            <SignIn />
          </section>
        </main>
      </SignedOut>
      <SignedIn>
    <main className="shell">
      <header className="topbar">
        <h1>Valore365</h1>
        <div className="topbar-actions">
          <span className="badge">Frontend V1 - React + Vite</span>
          <UserButton />
        </div>
      </header>

      <section className="panel ops-panel">
        <h2>Operazioni Dati</h2>
        <div className="ops-actions">
          <button type="button" className="secondary-btn" onClick={handleRefreshPricesNow} disabled={refreshingPrices || loading}>
            {refreshingPrices ? "Refresh in corso..." : "Refresh prezzi ora"}
          </button>
          <button type="button" className="secondary-btn" onClick={handleBackfillOneYear} disabled={runningBackfill || loading}>
            {runningBackfill ? "Backfill in corso..." : "Backfill 1Y"}
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>Aggiungi Titolo Rapido</h2>
        <form className="quick-form" onSubmit={handleQuickAddSubmit}>
          <label className="suggestion-host">
            Symbol*
            <input
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value);
                setSelectedExistingAsset(null);
              }}
              placeholder="AAPL"
              required
            />
            {assetSuggestions.length > 0 && !selectedExistingAsset && (
              <div className="suggestions">
                {assetSuggestions.map((item) => (
                  <button
                    key={`${item.id}-${item.symbol}`}
                    type="button"
                    className="suggestion-item"
                    onClick={() => {
                      setSelectedExistingAsset(item);
                      setSymbol(item.symbol);
                      setName(item.name ?? "");
                      setProviderSymbol(item.symbol);
                      setAssetSuggestions([]);
                    }}
                  >
                    <span>{item.symbol}</span>
                    <small>{item.name}</small>
                  </button>
                ))}
              </div>
            )}
          </label>
          <label>
            Nome
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Apple Inc." />
          </label>
          <label>
            Tipo
            <select value={assetType} onChange={(e) => setAssetType(e.target.value as AssetType)} disabled={!!selectedExistingAsset}>
              <option value="stock">stock</option>
              <option value="etf">etf</option>
              <option value="crypto">crypto</option>
              <option value="bond">bond</option>
              <option value="cash">cash</option>
              <option value="fund">fund</option>
            </select>
          </label>
          <label>
            Quote CCY*
            <input value={quoteCurrency} onChange={(e) => setQuoteCurrency(e.target.value)} placeholder="USD" required />
          </label>
          <label>
            Exchange Code
            <input value={exchangeCode} onChange={(e) => setExchangeCode(e.target.value)} placeholder="XNAS" disabled={!!selectedExistingAsset} />
          </label>
          <label>
            Provider Symbol
            <input value={providerSymbol} onChange={(e) => setProviderSymbol(e.target.value)} placeholder="AAPL" disabled={!!selectedExistingAsset} />
          </label>
          <label>
            Exchange Name
            <input value={exchangeName} onChange={(e) => setExchangeName(e.target.value)} placeholder="NASDAQ" disabled={!!selectedExistingAsset} />
          </label>
          <label>
            ISIN
            <input value={isin} onChange={(e) => setIsin(e.target.value)} placeholder="US0378331005" disabled={!!selectedExistingAsset} />
          </label>

          <label className="checkbox-row">
            <input type="checkbox" checked={autoBuy} onChange={(e) => setAutoBuy(e.target.checked)} />
            Crea anche acquisto iniziale
          </label>
          <label>
            Qty Buy
            <input value={buyQuantity} onChange={(e) => setBuyQuantity(e.target.value)} type="number" step="0.0001" min="0" />
          </label>
          <label>
            Price Buy
            <input value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} type="number" step="0.0001" min="0" />
          </label>

          <button type="submit" className="primary-btn" disabled={submitting}>
            {submitting ? "Inserimento..." : selectedExistingAsset ? "Aggiungi Posizione" : "Aggiungi Titolo"}
          </button>
        </form>
        {selectedExistingAsset && (
          <p className="hint">Usando titolo gia presente: {selectedExistingAsset.symbol} ({selectedExistingAsset.name})</p>
        )}
      </section>

      {loading && <p className="state">Caricamento dati portfolio...</p>}

      {!loading && summary && (
        <>
          <section className="kpi-grid">
            <article className="kpi-card">
              <h2>Valore Totale</h2>
              <p>{currencyFormatter.format(summary.market_value)}</p>
            </article>
            <article className="kpi-card">
              <h2>P/L Non Realizzato</h2>
              <p className={pnlToneClass}>
                {currencyFormatter.format(summary.unrealized_pl)} ({percentFormatter.format(summary.unrealized_pl_pct / 100)})
              </p>
            </article>
            <article className="kpi-card">
              <h2>Delta 1Y</h2>
              <p className={deltaToneClass}>{currencyFormatter.format(deltaYear)}</p>
            </article>
          </section>

          <section className="panel">
            <h2>Andamento 1Y</h2>
            <p>
              Ultimo punto: {latestPoint?.date ?? "n/a"} - {latestPoint ? currencyFormatter.format(latestPoint.market_value) : currencyFormatter.format(0)}
            </p>
            <div className="range-switch">
              {chartRanges.map((rangeValue) => (
                <button
                  type="button"
                  key={rangeValue}
                  className={rangeValue === chartRange ? "range-btn active" : "range-btn"}
                  onClick={() => {
                    setChartRange(rangeValue);
                    setHoverIndex(null);
                  }}
                >
                  {rangeValue}
                </button>
              ))}
            </div>
            <div className="chart-wrap">
              {chartModel.path ? (
                <svg viewBox={`0 0 ${chartModel.width} ${chartModel.height}`} role="img" aria-label="Andamento valore portfolio su 1 anno">
                  {chartModel.yTicks.map((tick) => (
                    <g key={tick.y}>
                      <line className="y-grid-line" x1={chartModel.margin.left} y1={tick.y} x2={chartModel.width - chartModel.margin.right} y2={tick.y} />
                      <text className="axis-label axis-label-y" x={chartModel.margin.left - 10} y={tick.y + 4}>
                        {currencyFormatter.format(tick.value)}
                      </text>
                    </g>
                  ))}

                  {chartModel.xTicks.map((tick) => (
                    <text key={tick.label + tick.x} className="axis-label axis-label-x" x={tick.x} y={chartModel.height - 10} textAnchor="middle">
                      {tick.label}
                    </text>
                  ))}

                  <path d={chartModel.path} className="line-path" />

                  {hoverPoint && (
                    <g>
                      <line
                        className="hover-line"
                        x1={hoverPoint.coord.x}
                        y1={chartModel.margin.top}
                        x2={hoverPoint.coord.x}
                        y2={chartModel.height - chartModel.margin.bottom}
                      />
                      <circle className="hover-dot" cx={hoverPoint.coord.x} cy={hoverPoint.coord.y} r={4} />
                      <g transform={`translate(${hoverPoint.coord.x + 8}, ${hoverPoint.coord.y - 12})`}>
                        <rect className="tooltip-bg" rx={6} ry={6} width={140} height={40} />
                        <text className="tooltip-text" x={8} y={16}>
                          {formatDate(hoverPoint.data.date)}
                        </text>
                        <text className="tooltip-text" x={8} y={31}>
                          {currencyFormatter.format(hoverPoint.data.market_value)}
                        </text>
                      </g>
                    </g>
                  )}

                  <rect
                    className="hover-capture"
                    x={chartModel.margin.left}
                    y={chartModel.margin.top}
                    width={chartModel.plotWidth}
                    height={chartModel.plotHeight}
                    onMouseMove={onChartHover}
                    onMouseLeave={() => setHoverIndex(null)}
                  />
                </svg>
              ) : (
                <p className="hint">Dati insufficienti per il grafico.</p>
              )}
            </div>
            <div className="chart-legend">
              <span className="legend-item">
                <i className="legend-dot line" /> Valore portfolio
              </span>
              <span className="legend-item">
                <i className="legend-dot hover" /> Punto selezionato
              </span>
            </div>
          </section>

          <section className="panel">
            <h2>Allocazione (Top Posizioni)</h2>
            <div className="bar-list">
              {topAllocation.map((row) => (
                <div className="bar-row" key={row.symbol}>
                  <div className="bar-label">
                    <span>{row.symbol}</span>
                    <span>{row.weight.toFixed(2)}%</span>
                  </div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${Math.min(100, row.weight)}%` }} />
                  </div>
                </div>
              ))}
              {topAllocation.length === 0 && <p className="hint">Nessuna posizione disponibile.</p>}
            </div>
          </section>

          <section className="panel">
            <h2>Posizioni</h2>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg Cost</th>
                  <th>Market</th>
                  <th>Value</th>
                  <th>U/PnL%</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.asset_id}>
                    <td>{position.symbol}</td>
                    <td>{position.quantity}</td>
                    <td>{position.avg_cost}</td>
                    <td>{position.market_price}</td>
                    <td>{position.market_value}</td>
                    <td>{position.unrealized_pl_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.kind}`}>
            {toast.message}
          </div>
        ))}
      </div>
    </main>
      </SignedIn>
    </>
  );
}

export default App;
