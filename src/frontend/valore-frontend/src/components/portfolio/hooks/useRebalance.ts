import { useState } from 'react';
import {
  commitPortfolioRebalance,
  getPortfolioRebalancePreview,
} from '../../../services/api';
import type {
  RebalancePreviewResponse,
  RebalanceCommitResponse,
} from '../../../services/api';
import { STORAGE_KEYS } from '../../dashboard/constants';

const getDefaultBrokerFee = (): number => {
  if (typeof window === 'undefined') return 0;
  const raw = window.localStorage.getItem(STORAGE_KEYS.brokerDefaultFee);
  if (raw == null || raw === '') return 0;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

const currentDateTimeLocalValue = () => {
  const now = new Date();
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
};

export function useRebalance(
  selectedPortfolioId: string | null,
  isMobile: boolean | undefined,
  loadTransactions: (portfolioId: number) => Promise<unknown>,
  setFormSuccess: (msg: string) => void,
) {
  const [previewOpened, setPreviewOpened] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<RebalancePreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<RebalanceCommitResponse | null>(null);
  const [commitLoading, setCommitLoading] = useState(false);
  const [selectedRows, setSelectedRows] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState<'buy_only' | 'rebalance' | 'sell_only'>('buy_only');
  const [maxTransactions, setMaxTransactions] = useState<number | string>(5);
  const [cashToAllocate, setCashToAllocate] = useState<number | string>(1000);
  const [minOrderValue, setMinOrderValue] = useState<number | string>(100);
  const [rounding, setRounding] = useState<'fractional' | 'integer'>('fractional');
  const [tradeAt, setTradeAt] = useState('');

  const openPreviewModal = () => {
    if (isMobile) return;
    setPreviewError(null);
    setPreviewData(null);
    setCommitResult(null);
    setSelectedRows({});
    setTradeAt(currentDateTimeLocalValue());
    setPreviewOpened(true);
  };

  const handleLoadPreview = async () => {
    const portfolioId = Number(selectedPortfolioId);
    const maxTx = typeof maxTransactions === 'number' ? maxTransactions : Number(maxTransactions);
    const cash = typeof cashToAllocate === 'number' ? cashToAllocate : Number(cashToAllocate);
    const minOrder = typeof minOrderValue === 'number' ? minOrderValue : Number(minOrderValue || 0);

    setPreviewError(null);
    setPreviewData(null);
    setCommitResult(null);

    if (!Number.isFinite(portfolioId)) {
      setPreviewError('Seleziona un portfolio valido');
      return;
    }
    if (!Number.isFinite(maxTx) || maxTx < 1) {
      setPreviewError('Numero massimo transazioni non valido');
      return;
    }
    if (!Number.isFinite(minOrder) || minOrder < 0) {
      setPreviewError('Soglia minima ordine non valida');
      return;
    }
    if (mode === 'buy_only' && (!Number.isFinite(cash) || cash <= 0)) {
      setPreviewError('Importo da allocare obbligatorio e > 0 in modalità acquisto');
      return;
    }

    try {
      setPreviewLoading(true);
      const response = await getPortfolioRebalancePreview(portfolioId, {
        mode,
        max_transactions: Math.min(100, Math.max(1, Math.trunc(maxTx))),
        cash_to_allocate: mode === 'buy_only' ? cash : null,
        min_order_value: minOrder,
        trade_at: tradeAt ? new Date(tradeAt).toISOString() : null,
        rounding,
        selection_strategy: 'largest_drift',
        use_latest_prices: true,
      });
      setPreviewData(response);
      setSelectedRows(
        Object.fromEntries(response.items.map((item) => [`${item.asset_id}-${item.side}`, true])),
      );
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Errore generazione preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCommitPreview = async () => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) {
      setPreviewError('Seleziona un portfolio valido');
      return;
    }
    if (!previewData) {
      setPreviewError('Genera prima una preview');
      return;
    }
    if (!tradeAt) {
      setPreviewError('Data/ora operazioni obbligatoria');
      return;
    }

    const selectedItems = previewData.items.filter((item) => selectedRows[`${item.asset_id}-${item.side}`]);
    if (selectedItems.length === 0) {
      setPreviewError('Seleziona almeno una riga da creare');
      return;
    }

    setPreviewError(null);
    setCommitResult(null);

    try {
      setCommitLoading(true);
      const result = await commitPortfolioRebalance(portfolioId, {
        trade_at: new Date(tradeAt).toISOString(),
        items: selectedItems.map((item) => ({
          asset_id: item.asset_id,
          side: item.side,
          quantity: item.quantity,
          price: item.price,
          fees: getDefaultBrokerFee(),
          taxes: 0,
          notes: 'Generata da target allocation',
        })),
      });
      setCommitResult(result);
      await loadTransactions(portfolioId);
      setFormSuccess(
        `Ribilanciamento: create ${result.created} transazioni${result.failed ? `, fallite ${result.failed}` : ''}.`,
      );
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Errore creazione transazioni da preview');
    } finally {
      setCommitLoading(false);
    }
  };

  return {
    previewOpened,
    setPreviewOpened,
    previewError,
    previewData,
    previewLoading,
    commitResult,
    commitLoading,
    selectedRows,
    setSelectedRows,
    mode,
    setMode,
    maxTransactions,
    setMaxTransactions,
    cashToAllocate,
    setCashToAllocate,
    minOrderValue,
    setMinOrderValue,
    rounding,
    setRounding,
    tradeAt,
    setTradeAt,
    openPreviewModal,
    handleLoadPreview,
    handleCommitPreview,
  };
}
