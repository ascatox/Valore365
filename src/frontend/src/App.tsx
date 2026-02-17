import { useCallback, useEffect, useMemo, useState } from "react";
import { SignIn, SignedIn, SignedOut, UserButton, useAuth } from "@clerk/clerk-react";

import { backfillDaily, getPositions, getSummary, getTimeSeries, refreshPrices } from "./api";
import { ToastStack, type ToastItem, type ToastKind } from "./components/molecules";
import { AllocationBars, KpiGrid, OpsPanel, PortfolioLineChart, PositionsTable, QuickAddForm } from "./components/organisms";
import type { PortfolioSummary, Position, TimeSeriesPoint } from "./types";

const defaultPortfolioId = Number(import.meta.env.VITE_DEFAULT_PORTFOLIO_ID ?? 1);

function App() {
  const { getToken } = useAuth();
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [timeseries, setTimeseries] = useState<TimeSeriesPoint[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshingPrices, setRefreshingPrices] = useState<boolean>(false);
  const [runningBackfill, setRunningBackfill] = useState<boolean>(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

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

  const deltaYear = useMemo(() => {
    const latestPoint = timeseries[timeseries.length - 1];
    const firstPoint = timeseries[0];
    if (!latestPoint || !firstPoint) {
      return 0;
    }
    return latestPoint.market_value - firstPoint.market_value;
  }, [timeseries]);

  const handleRefreshPricesNow = useCallback(async () => {
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
  }, [getAccessToken, loadDashboard, pushToast]);

  const handleBackfillOneYear = useCallback(async () => {
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
  }, [getAccessToken, loadDashboard, pushToast]);

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

          <OpsPanel
            loading={loading}
            refreshingPrices={refreshingPrices}
            runningBackfill={runningBackfill}
            onRefreshPrices={handleRefreshPricesNow}
            onBackfillOneYear={handleBackfillOneYear}
          />

          <QuickAddForm portfolioId={defaultPortfolioId} getAccessToken={getAccessToken} onToast={pushToast} onCompleted={loadDashboard} />

          {loading && <p className="state">Caricamento dati portfolio...</p>}

          {!loading && summary && (
            <>
              <KpiGrid summary={summary} deltaYear={deltaYear} currencyFormatter={currencyFormatter} percentFormatter={percentFormatter} />
              <PortfolioLineChart timeseries={timeseries} currencyFormatter={currencyFormatter} />
              <AllocationBars positions={positions} />
              <PositionsTable positions={positions} />
            </>
          )}

          <ToastStack toasts={toasts} />
        </main>
      </SignedIn>
    </>
  );
}

export default App;
