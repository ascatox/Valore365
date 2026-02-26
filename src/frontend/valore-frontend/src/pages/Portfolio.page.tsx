import { useEffect, useMemo, useState } from 'react';
import { useMediaQuery } from '@mantine/hooks';
import {
  Table,
  Button,
  Text,
  Group,
  Title,
  Select,
  Alert,
  Loader,
  Drawer,
  Modal,
  Stack,
  NumberInput,
  ActionIcon,
  TextInput,
  SegmentedControl,
  Menu,
  Tooltip,
  Checkbox,
} from '@mantine/core';
import { IconEdit, IconPlus, IconTrash, IconDotsVertical, IconArrowsExchange, IconTarget } from '@tabler/icons-react';
import { TargetAllocationSection } from '../components/portfolio/TargetAllocationSection.tsx';
import { TransactionsSection } from '../components/portfolio/TransactionsSection.tsx';
import {
  createTransaction,
  deleteTransaction,
  createPortfolio,
  deletePortfolio,
  deletePortfolioTargetAllocation,
  discoverAssets,
  ensureAsset,
  getAdminPortfolios,
  getAssetLatestQuote,
  getPortfolioTargetAllocation,
  commitPortfolioRebalance,
  getPortfolioRebalancePreview,
  getPortfolioTransactions,
  updateTransaction,
  updatePortfolio,
  upsertPortfolioTargetAllocation,
} from '../services/api';
import type {
  AssetDiscoverItem,
  Portfolio,
  PortfolioTargetAllocationItem,
  RebalancePreviewResponse,
  RebalanceCommitResponse,
  TransactionListItem,
} from '../services/api';

import { STORAGE_KEYS } from '../components/dashboard/constants';

export function PortfolioPage() {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null);
  const [allocations, setAllocations] = useState<PortfolioTargetAllocationItem[]>([]);
  const [loadingPortfolios, setLoadingPortfolios] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<TransactionListItem[]>([]);
  const [loadingTransactions, setLoadingTransactions] = useState(false);
  const [deletingTransactionId, setDeletingTransactionId] = useState<number | null>(null);
  const [transactionDeleteOpened, setTransactionDeleteOpened] = useState(false);
  const [transactionIdToDelete, setTransactionIdToDelete] = useState<number | null>(null);
  const [transactionLabelToDelete, setTransactionLabelToDelete] = useState<string | null>(null);
  const [transactionFilterQuery, setTransactionFilterQuery] = useState('');
  const [transactionFilterSide, setTransactionFilterSide] = useState<string>('all');
  const [transactionSortKey, setTransactionSortKey] = useState<'trade_at' | 'symbol' | 'side' | 'value'>('trade_at');
  const [transactionSortDir, setTransactionSortDir] = useState<'asc' | 'desc'>('desc');
  const [editTransactionOpened, setEditTransactionOpened] = useState(false);
  const [editingTransactionId, setEditingTransactionId] = useState<number | null>(null);
  const [editTransactionLabel, setEditTransactionLabel] = useState<string | null>(null);
  const [editTradeAt, setEditTradeAt] = useState('');
  const [editQuantity, setEditQuantity] = useState<number | string>('');
  const [editPrice, setEditPrice] = useState<number | string>('');
  const [editFees, setEditFees] = useState<number | string>(0);
  const [editTaxes, setEditTaxes] = useState<number | string>(0);
  const [editNotes, setEditNotes] = useState('');
  const [editTransactionError, setEditTransactionError] = useState<string | null>(null);
  const [editTransactionSaving, setEditTransactionSaving] = useState(false);

  const [drawerOpened, setDrawerOpened] = useState(false);
  const [transactionDrawerOpened, setTransactionDrawerOpened] = useState(false);
  const [formSaving, setFormSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [portfolioModalOpened, setPortfolioModalOpened] = useState(false);
  const [portfolioModalMode, setPortfolioModalMode] = useState<'create' | 'edit'>('create');
  const [portfolioDeleteOpened, setPortfolioDeleteOpened] = useState(false);
  const [portfolioSaving, setPortfolioSaving] = useState(false);
  const [portfolioDeleting, setPortfolioDeleting] = useState(false);
  const [portfolioFormError, setPortfolioFormError] = useState<string | null>(null);
  const [portfolioFormName, setPortfolioFormName] = useState('');
  const [portfolioFormBaseCurrency, setPortfolioFormBaseCurrency] = useState('EUR');
  const [portfolioFormTimezone, setPortfolioFormTimezone] = useState('Europe/Rome');
  const [portfolioFormTargetNotional, setPortfolioFormTargetNotional] = useState<number | string>('');
  const [portfolioFormCashBalance, setPortfolioFormCashBalance] = useState<number | string>(0);
  const [portfolioView, setPortfolioView] = useState<'transactions' | 'target'>('transactions');

  const [targetWeight, setTargetWeight] = useState<number | string>(0);

  const [discoverQuery, setDiscoverQuery] = useState('');
  const [discoverItems, setDiscoverItems] = useState<AssetDiscoverItem[]>([]);
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [discoverSelectionKey, setDiscoverSelectionKey] = useState<string | null>(null);
  const [resolvedAssetId, setResolvedAssetId] = useState<number | null>(null);
  const [resolvedAssetLabel, setResolvedAssetLabel] = useState<string | null>(null);
  const [ensuringAsset, setEnsuringAsset] = useState(false);
  const [txFormError, setTxFormError] = useState<string | null>(null);
  const [txFormSuccess, setTxFormSuccess] = useState<string | null>(null);
  const [txFormSaving, setTxFormSaving] = useState(false);
  const [txSide, setTxSide] = useState<'buy' | 'sell'>('buy');
  const [txTradeAt, setTxTradeAt] = useState('');
  const [txQuantity, setTxQuantity] = useState<number | string>('');
  const [txPrice, setTxPrice] = useState<number | string>('');
  const [txFees, setTxFees] = useState<number | string>(0);
  const [txTaxes, setTxTaxes] = useState<number | string>(0);
  const [txNotes, setTxNotes] = useState('');
  const [txDiscoverQuery, setTxDiscoverQuery] = useState('');
  const [txDiscoverItems, setTxDiscoverItems] = useState<AssetDiscoverItem[]>([]);
  const [txDiscoverLoading, setTxDiscoverLoading] = useState(false);
  const [txDiscoverSelectionKey, setTxDiscoverSelectionKey] = useState<string | null>(null);
  const [txResolvedAssetId, setTxResolvedAssetId] = useState<number | null>(null);
  const [txResolvedAssetLabel, setTxResolvedAssetLabel] = useState<string | null>(null);
  const [txEnsuringAsset, setTxEnsuringAsset] = useState(false);
  const [txPriceLoading, setTxPriceLoading] = useState(false);
  const [rebalancePreviewOpened, setRebalancePreviewOpened] = useState(false);
  const [rebalancePreviewLoading, setRebalancePreviewLoading] = useState(false);
  const [rebalancePreviewError, setRebalancePreviewError] = useState<string | null>(null);
  const [rebalancePreviewData, setRebalancePreviewData] = useState<RebalancePreviewResponse | null>(null);
  const [rebalanceCommitResult, setRebalanceCommitResult] = useState<RebalanceCommitResponse | null>(null);
  const [rebalanceCommitLoading, setRebalanceCommitLoading] = useState(false);
  const [rebalanceSelectedRows, setRebalanceSelectedRows] = useState<Record<string, boolean>>({});
  const [rebalanceMode, setRebalanceMode] = useState<'buy_only' | 'rebalance' | 'sell_only'>('buy_only');
  const [rebalanceMaxTransactions, setRebalanceMaxTransactions] = useState<number | string>(5);
  const [rebalanceCashToAllocate, setRebalanceCashToAllocate] = useState<number | string>(1000);
  const [rebalanceMinOrderValue, setRebalanceMinOrderValue] = useState<number | string>(100);
  const [rebalanceRounding, setRebalanceRounding] = useState<'fractional' | 'integer'>('fractional');
  const [rebalanceTradeAt, setRebalanceTradeAt] = useState('');

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const formatMoney = (value: number | null | undefined, currency?: string | null) => {
    if (value == null || !Number.isFinite(value)) return 'N/D';
    return new Intl.NumberFormat('it-IT', {
      style: 'currency',
      currency: currency || 'EUR',
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatDateTime = (value: string) => {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return value;
    return dt.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatTransactionSideLabel = (side: 'buy' | 'sell') => (side === 'buy' ? 'Acquisto' : 'Vendita');

  const getDefaultBrokerFee = (): number => {
    if (typeof window === 'undefined') return 0;
    const raw = window.localStorage.getItem(STORAGE_KEYS.brokerDefaultFee);
    if (raw == null || raw === '') return 0;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
  };

  const toNumericInputValue = (value: number | string | null | undefined): number | null => {
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed) return null;
      const parsed = Number(trimmed.replace(',', '.'));
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };

  const formatGrossTotal = (quantity: number | string, price: number | string): string => {
    const q = toNumericInputValue(quantity);
    const p = toNumericInputValue(price);
    if (q == null || p == null) return '';
    const total = q * p;
    return new Intl.NumberFormat('it-IT', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(total);
  };

  const currentDateTimeLocalValue = () => {
    const now = new Date();
    const pad = (v: number) => String(v).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  };

  const loadTargetAllocation = async (portfolioId: number) => {
    const rows = await getPortfolioTargetAllocation(portfolioId);
    setAllocations(rows);
    return rows;
  };

  const loadTransactions = async (portfolioId: number) => {
    const rows = await getPortfolioTransactions(portfolioId);
    setTransactions(rows);
    return rows;
  };

  const loadPortfolios = async (preferredSelectedId?: string | null) => {
    const items = await getAdminPortfolios();
    setPortfolios(items);
    setSelectedPortfolioId((prev) => {
      const candidate = preferredSelectedId ?? prev;
      const exists = candidate ? items.some((p) => String(p.id) === candidate) : false;
      const nextSelected = exists ? candidate : (items[0] ? String(items[0].id) : null);
      if (typeof window !== 'undefined') {
        if (nextSelected) {
          window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, nextSelected);
        } else {
          window.localStorage.removeItem(STORAGE_KEYS.selectedPortfolioId);
        }
      }
      return nextSelected;
    });
    return items;
  };

  const resetForm = () => {
    setTargetWeight(0);
    setDiscoverQuery('');
    setDiscoverItems([]);
    setDiscoverLoading(false);
    setDiscoverSelectionKey(null);
    setResolvedAssetId(null);
    setResolvedAssetLabel(null);
    setEnsuringAsset(false);
    setFormError(null);
    setFormSuccess(null);
  };

  const resetTransactionForm = () => {
    setTxFormError(null);
    setTxFormSuccess(null);
    setTxFormSaving(false);
    setTxSide('buy');
    setTxTradeAt(currentDateTimeLocalValue());
    setTxQuantity('');
    setTxPrice('');
    setTxFees(getDefaultBrokerFee());
    setTxTaxes(0);
    setTxNotes('');
    setTxDiscoverQuery('');
    setTxDiscoverItems([]);
    setTxDiscoverLoading(false);
    setTxDiscoverSelectionKey(null);
    setTxResolvedAssetId(null);
    setTxResolvedAssetLabel(null);
    setTxEnsuringAsset(false);
  };

  useEffect(() => {
    let active = true;
    setLoadingPortfolios(true);
    setError(null);

    loadPortfolios()
      .then(() => {
        if (!active) return;
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento portafogli');
      })
      .finally(() => {
        if (active) setLoadingPortfolios(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (isMobile && rebalancePreviewOpened) {
      setRebalancePreviewOpened(false);
    }
  }, [isMobile, rebalancePreviewOpened]);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setAllocations([]);
      return;
    }
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    let active = true;
    setLoadingData(true);
    setError(null);

    loadTargetAllocation(portfolioId)
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento allocazione target');
      })
      .finally(() => {
        if (active) setLoadingData(false);
      });

    return () => {
      active = false;
    };
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setTransactions([]);
      setTransactionsError(null);
      return;
    }
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    let active = true;
    setLoadingTransactions(true);
    setTransactionsError(null);

    loadTransactions(portfolioId)
      .catch((err) => {
        if (!active) return;
        setTransactionsError(err instanceof Error ? err.message : 'Errore nel caricamento transazioni');
      })
      .finally(() => {
        if (active) setLoadingTransactions(false);
      });

    return () => {
      active = false;
    };
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!drawerOpened) return;
    const q = discoverQuery.trim();
    if (!q) {
      setDiscoverItems([]);
      setDiscoverLoading(false);
      return;
    }

    let active = true;
    setDiscoverLoading(true);
    const timer = window.setTimeout(() => {
      discoverAssets(q)
        .then((items) => {
          if (active) setDiscoverItems(items);
        })
        .catch(() => {
          if (active) setDiscoverItems([]);
        })
        .finally(() => {
          if (active) setDiscoverLoading(false);
        });
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [discoverQuery, drawerOpened]);

  useEffect(() => {
    if (!transactionDrawerOpened) return;
    const q = txDiscoverQuery.trim();
    if (!q) {
      setTxDiscoverItems([]);
      setTxDiscoverLoading(false);
      return;
    }

    let active = true;
    setTxDiscoverLoading(true);
    const timer = window.setTimeout(() => {
      discoverAssets(q)
        .then((items) => {
          if (active) setTxDiscoverItems(items);
        })
        .catch(() => {
          if (active) setTxDiscoverItems([]);
        })
        .finally(() => {
          if (active) setTxDiscoverLoading(false);
        });
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [txDiscoverQuery, transactionDrawerOpened]);

  const totalWeight = useMemo(
    () => allocations.reduce((sum, item) => sum + item.weight_pct, 0),
    [allocations],
  );
  const portfolioTargetNotional = selectedPortfolio?.target_notional ?? null;
  const assignedTargetValue = useMemo(
    () => (portfolioTargetNotional != null ? (portfolioTargetNotional * totalWeight) / 100 : null),
    [portfolioTargetNotional, totalWeight],
  );

  const openDrawer = () => {
    resetForm();
    setDrawerOpened(true);
  };

  const openTransactionDrawer = () => {
    resetTransactionForm();
    setTransactionDrawerOpened(true);
  };

  const openRebalancePreviewModal = () => {
    if (isMobile) return;
    setRebalancePreviewError(null);
    setRebalancePreviewData(null);
    setRebalanceCommitResult(null);
    setRebalanceSelectedRows({});
    setRebalanceTradeAt(currentDateTimeLocalValue());
    setRebalancePreviewOpened(true);
  };

  const openCreatePortfolioModal = () => {
    setPortfolioModalMode('create');
    setPortfolioFormName('');
    setPortfolioFormBaseCurrency('EUR');
    setPortfolioFormTimezone('Europe/Rome');
    setPortfolioFormTargetNotional('');
    setPortfolioFormCashBalance(0);
    setPortfolioFormError(null);
    setPortfolioModalOpened(true);
  };

  const openEditPortfolioModal = () => {
    if (!selectedPortfolio) return;
    setPortfolioModalMode('edit');
    setPortfolioFormName(selectedPortfolio.name);
    setPortfolioFormBaseCurrency(selectedPortfolio.base_currency);
    setPortfolioFormTimezone(selectedPortfolio.timezone);
    setPortfolioFormTargetNotional(selectedPortfolio.target_notional ?? '');
    setPortfolioFormCashBalance(selectedPortfolio.cash_balance ?? 0);
    setPortfolioFormError(null);
    setPortfolioModalOpened(true);
  };

  const handleSavePortfolio = async () => {
    setPortfolioFormError(null);
    const name = portfolioFormName.trim();
    const baseCurrency = portfolioFormBaseCurrency.trim().toUpperCase();
    const timezone = portfolioFormTimezone.trim();
    const normalizedTargetNotional =
      portfolioFormTargetNotional === '' || portfolioFormTargetNotional === null
        ? null
        : typeof portfolioFormTargetNotional === 'number'
          ? portfolioFormTargetNotional
          : Number(portfolioFormTargetNotional);
    if (!name) {
      setPortfolioFormError('Nome portfolio obbligatorio');
      return;
    }
    if (!/^[A-Z]{3}$/.test(baseCurrency)) {
      setPortfolioFormError('Valuta base non valida (es. EUR)');
      return;
    }
    if (!timezone) {
      setPortfolioFormError('Timezone obbligatoria');
      return;
    }
    if (normalizedTargetNotional !== null && (!Number.isFinite(normalizedTargetNotional) || normalizedTargetNotional < 0)) {
      setPortfolioFormError('Controvalore target non valido');
      return;
    }
    const normalizedCashBalance = portfolioFormCashBalance === '' ? 0 : Number(portfolioFormCashBalance);
    if (!Number.isFinite(normalizedCashBalance) || normalizedCashBalance < 0) {
      setPortfolioFormError('Cash disponibile non valido');
      return;
    }

    try {
      setPortfolioSaving(true);
      if (portfolioModalMode === 'create') {
        const created = await createPortfolio({
          name,
          base_currency: baseCurrency,
          timezone,
          target_notional: normalizedTargetNotional,
          cash_balance: normalizedCashBalance,
        });
        await loadPortfolios(String(created.id));
        setFormSuccess(`Portfolio "${created.name}" creato`);
      } else {
        const portfolioId = Number(selectedPortfolioId);
        if (!Number.isFinite(portfolioId)) {
          setPortfolioFormError('Seleziona un portfolio valido');
          return;
        }
        const updated = await updatePortfolio(portfolioId, {
          name,
          base_currency: baseCurrency,
          timezone,
          target_notional: normalizedTargetNotional,
          cash_balance: normalizedCashBalance,
        });
        await loadPortfolios(String(updated.id));
        setFormSuccess(`Portfolio "${updated.name}" aggiornato`);
      }
      setPortfolioModalOpened(false);
    } catch (err) {
      setPortfolioFormError(err instanceof Error ? err.message : 'Errore salvataggio portfolio');
    } finally {
      setPortfolioSaving(false);
    }
  };

  const handleDeletePortfolio = async () => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    try {
      setPortfolioDeleting(true);
      await deletePortfolio(portfolioId);
      await loadPortfolios(null);
      setPortfolioDeleteOpened(false);
      setFormSuccess('Portfolio eliminato');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore eliminazione portfolio');
    } finally {
      setPortfolioDeleting(false);
    }
  };

  const handleDiscoverSelection = async (value: string | null) => {
    setDiscoverSelectionKey(value);
    setFormError(null);
    setFormSuccess(null);
    setResolvedAssetId(null);
    setResolvedAssetLabel(null);

    if (!value) return;
    const selected = discoverItems.find((item) => item.key === value);
    if (!selected) return;

    const label = `${selected.symbol} - ${selected.name ?? 'N/D'}${selected.exchange ? ` (${selected.exchange})` : ''}`;

    if (selected.source === 'db' && selected.asset_id) {
      setResolvedAssetId(selected.asset_id);
      setResolvedAssetLabel(label);
      return;
    }

    try {
      setEnsuringAsset(true);
      const portfolioId = Number(selectedPortfolioId);
      const ensured = await ensureAsset({
        source: selected.source,
        asset_id: selected.asset_id,
        symbol: selected.symbol,
        name: selected.name,
        exchange: selected.exchange,
        provider: selected.provider ?? 'yfinance',
        provider_symbol: selected.provider_symbol ?? selected.symbol,
        portfolio_id: Number.isFinite(portfolioId) ? portfolioId : undefined,
      });
      setResolvedAssetId(ensured.asset_id);
      setResolvedAssetLabel(label);
      if (ensured.created) {
        setFormSuccess(`Asset ${ensured.symbol} creato e selezionato.`);
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Errore nella risoluzione asset');
    } finally {
      setEnsuringAsset(false);
    }
  };

  const handleSaveTargetWeight = async () => {
    setFormError(null);
    setFormSuccess(null);
    const portfolioId = Number(selectedPortfolioId);
    const normalizedWeight = typeof targetWeight === 'number' ? targetWeight : Number(targetWeight);

    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setFormError('Seleziona un portfolio valido');
      return;
    }
    if (!resolvedAssetId) {
      setFormError('Seleziona un asset dalla ricerca');
      return;
    }
    if (!Number.isFinite(normalizedWeight) || normalizedWeight < 0 || normalizedWeight > 100) {
      setFormError('Il peso deve essere tra 0 e 100');
      return;
    }

    try {
      setFormSaving(true);
      await upsertPortfolioTargetAllocation(portfolioId, {
        asset_id: resolvedAssetId,
        weight_pct: normalizedWeight,
      });
      await loadTargetAllocation(portfolioId);
      setDrawerOpened(false);
      resetForm();
      setFormSuccess('Peso salvato. Caricamento storico prezzi in corso...');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Errore salvataggio peso');
    } finally {
      setFormSaving(false);
    }
  };

  const handleDeleteAllocation = async (assetIdToDelete: number) => {
    const portfolioId = Number(selectedPortfolioId);
    if (!portfolioId) return;
    setError(null);
    try {
      await deletePortfolioTargetAllocation(portfolioId, assetIdToDelete);
      await loadTargetAllocation(portfolioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore rimozione asset dal portafoglio');
    }
  };

  const handleTransactionDiscoverSelection = async (value: string | null) => {
    setTxDiscoverSelectionKey(value);
    setTxFormError(null);
    setTxFormSuccess(null);
    setTxResolvedAssetId(null);
    setTxResolvedAssetLabel(null);
    setTxPrice('');

    if (!value) return;
    const selected = txDiscoverItems.find((item) => item.key === value);
    if (!selected) return;

    const label = `${selected.symbol} - ${selected.name ?? 'N/D'}${selected.exchange ? ` (${selected.exchange})` : ''}`;

    const fetchPrice = async (assetId: number) => {
      setTxPriceLoading(true);
      try {
        const quote = await getAssetLatestQuote(assetId);
        setTxPrice(quote.price);
      } catch {
        // prezzo non disponibile — l'utente lo inserisce manualmente
      } finally {
        setTxPriceLoading(false);
      }
    };

    if (selected.source === 'db' && selected.asset_id) {
      setTxResolvedAssetId(selected.asset_id);
      setTxResolvedAssetLabel(label);
      void fetchPrice(selected.asset_id);
      return;
    }

    try {
      setTxEnsuringAsset(true);
      const portfolioId = Number(selectedPortfolioId);
      const ensured = await ensureAsset({
        source: selected.source,
        asset_id: selected.asset_id,
        symbol: selected.symbol,
        name: selected.name,
        exchange: selected.exchange,
        provider: selected.provider ?? 'yfinance',
        provider_symbol: selected.provider_symbol ?? selected.symbol,
        portfolio_id: Number.isFinite(portfolioId) ? portfolioId : undefined,
      });
      setTxResolvedAssetId(ensured.asset_id);
      setTxResolvedAssetLabel(label);
      if (ensured.created) {
        setTxFormSuccess(`Asset ${ensured.symbol} creato e selezionato.`);
      }
      void fetchPrice(ensured.asset_id);
    } catch (err) {
      setTxFormError(err instanceof Error ? err.message : 'Errore nella risoluzione asset');
    } finally {
      setTxEnsuringAsset(false);
    }
  };

  const handleCreateTransaction = async () => {
    const portfolioId = Number(selectedPortfolioId);
    const quantity = typeof txQuantity === 'number' ? txQuantity : Number(txQuantity);
    const price = typeof txPrice === 'number' ? txPrice : Number(txPrice);
    const fees = typeof txFees === 'number' ? txFees : Number(txFees || 0);
    const taxes = typeof txTaxes === 'number' ? txTaxes : Number(txTaxes || 0);

    setTxFormError(null);
    setTxFormSuccess(null);

    if (!Number.isFinite(portfolioId)) {
      setTxFormError('Seleziona un portfolio valido');
      return;
    }
    if (!txResolvedAssetId) {
      setTxFormError('Seleziona un asset');
      return;
    }
    if (!txTradeAt) {
      setTxFormError('Data/ora operazione obbligatoria');
      return;
    }
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setTxFormError('Quantita non valida');
      return;
    }
    if (!Number.isFinite(price) || price < 0) {
      setTxFormError('Prezzo non valido');
      return;
    }
    if (!Number.isFinite(fees) || fees < 0 || !Number.isFinite(taxes) || taxes < 0) {
      setTxFormError('Fee/tasse non validi');
      return;
    }

    try {
      setTxFormSaving(true);
      await createTransaction({
        portfolio_id: portfolioId,
        asset_id: txResolvedAssetId,
        side: txSide,
        trade_at: new Date(txTradeAt).toISOString(),
        quantity,
        price,
        fees,
        taxes,
        trade_currency: selectedPortfolio?.base_currency ?? 'EUR',
        notes: txNotes.trim() || null,
      });
      await loadTransactions(portfolioId);
      setTxFormSuccess('Transazione salvata. Caricamento storico prezzi in corso...');
      setTransactionDrawerOpened(false);
      resetTransactionForm();
    } catch (err) {
      setTxFormError(err instanceof Error ? err.message : 'Errore salvataggio transazione');
    } finally {
      setTxFormSaving(false);
    }
  };

  const handleDeleteTransaction = async (transactionId: number) => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    setTransactionsError(null);
    try {
      setDeletingTransactionId(transactionId);
      await deleteTransaction(transactionId);
      await loadTransactions(portfolioId);
      setFormSuccess('Transazione eliminata');
    } catch (err) {
      setTransactionsError(err instanceof Error ? err.message : 'Errore eliminazione transazione');
    } finally {
      setDeletingTransactionId(null);
    }
  };

  const handleLoadRebalancePreview = async () => {
    const portfolioId = Number(selectedPortfolioId);
    const maxTransactions =
      typeof rebalanceMaxTransactions === 'number' ? rebalanceMaxTransactions : Number(rebalanceMaxTransactions);
    const cashToAllocate =
      typeof rebalanceCashToAllocate === 'number' ? rebalanceCashToAllocate : Number(rebalanceCashToAllocate);
    const minOrderValue =
      typeof rebalanceMinOrderValue === 'number' ? rebalanceMinOrderValue : Number(rebalanceMinOrderValue || 0);

    setRebalancePreviewError(null);
    setRebalancePreviewData(null);
    setRebalanceCommitResult(null);

    if (!Number.isFinite(portfolioId)) {
      setRebalancePreviewError('Seleziona un portfolio valido');
      return;
    }
    if (!Number.isFinite(maxTransactions) || maxTransactions < 1) {
      setRebalancePreviewError('Numero massimo transazioni non valido');
      return;
    }
    if (!Number.isFinite(minOrderValue) || minOrderValue < 0) {
      setRebalancePreviewError('Soglia minima ordine non valida');
      return;
    }
    if (rebalanceMode === 'buy_only' && (!Number.isFinite(cashToAllocate) || cashToAllocate <= 0)) {
      setRebalancePreviewError('Importo da allocare obbligatorio e > 0 in modalità acquisto');
      return;
    }

    try {
      setRebalancePreviewLoading(true);
      const response = await getPortfolioRebalancePreview(portfolioId, {
        mode: rebalanceMode,
        max_transactions: Math.min(100, Math.max(1, Math.trunc(maxTransactions))),
        cash_to_allocate: rebalanceMode === 'buy_only' ? cashToAllocate : null,
        min_order_value: minOrderValue,
        trade_at: rebalanceTradeAt ? new Date(rebalanceTradeAt).toISOString() : null,
        rounding: rebalanceRounding,
        selection_strategy: 'largest_drift',
        use_latest_prices: true,
      });
      setRebalancePreviewData(response);
      setRebalanceSelectedRows(
        Object.fromEntries(response.items.map((item) => [`${item.asset_id}-${item.side}`, true])),
      );
    } catch (err) {
      setRebalancePreviewError(err instanceof Error ? err.message : 'Errore generazione preview');
    } finally {
      setRebalancePreviewLoading(false);
    }
  };

  const handleCommitRebalancePreview = async () => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) {
      setRebalancePreviewError('Seleziona un portfolio valido');
      return;
    }
    if (!rebalancePreviewData) {
      setRebalancePreviewError('Genera prima una preview');
      return;
    }
    if (!rebalanceTradeAt) {
      setRebalancePreviewError('Data/ora operazioni obbligatoria');
      return;
    }

    const selectedItems = rebalancePreviewData.items.filter((item) => rebalanceSelectedRows[`${item.asset_id}-${item.side}`]);
    if (selectedItems.length === 0) {
      setRebalancePreviewError('Seleziona almeno una riga da creare');
      return;
    }

    setRebalancePreviewError(null);
    setRebalanceCommitResult(null);

    try {
      setRebalanceCommitLoading(true);
      const result = await commitPortfolioRebalance(portfolioId, {
        trade_at: new Date(rebalanceTradeAt).toISOString(),
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
      setRebalanceCommitResult(result);
      await loadTransactions(portfolioId);
      setFormSuccess(
        `Ribilanciamento: create ${result.created} transazioni${result.failed ? `, fallite ${result.failed}` : ''}.`,
      );
    } catch (err) {
      setRebalancePreviewError(err instanceof Error ? err.message : 'Errore creazione transazioni da preview');
    } finally {
      setRebalanceCommitLoading(false);
    }
  };

  const openDeleteTransactionModal = (tx: TransactionListItem) => {
    setTransactionIdToDelete(tx.id);
    setTransactionLabelToDelete(`${formatTransactionSideLabel(tx.side)} ${tx.symbol} (${tx.quantity})`);
    setTransactionDeleteOpened(true);
  };

  const confirmDeleteTransaction = async () => {
    if (!transactionIdToDelete) return;
    await handleDeleteTransaction(transactionIdToDelete);
    setTransactionDeleteOpened(false);
    setTransactionIdToDelete(null);
    setTransactionLabelToDelete(null);
  };

  const toLocalDateTimeInput = (value: string) => {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return '';
    const pad = (v: number) => String(v).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
  };

  const openEditTransactionModal = (tx: TransactionListItem) => {
    setEditTransactionError(null);
    setEditingTransactionId(tx.id);
    setEditTransactionLabel(`${tx.symbol} (${formatTransactionSideLabel(tx.side)})`);
    setEditTradeAt(toLocalDateTimeInput(tx.trade_at));
    setEditQuantity(tx.quantity);
    setEditPrice(tx.price);
    setEditFees(tx.fees ?? 0);
    setEditTaxes(tx.taxes ?? 0);
    setEditNotes(tx.notes ?? '');
    setEditTransactionOpened(true);
  };

  const handleUpdateTransaction = async () => {
    const portfolioId = Number(selectedPortfolioId);
    const quantity = typeof editQuantity === 'number' ? editQuantity : Number(editQuantity);
    const price = typeof editPrice === 'number' ? editPrice : Number(editPrice);
    const fees = typeof editFees === 'number' ? editFees : Number(editFees || 0);
    const taxes = typeof editTaxes === 'number' ? editTaxes : Number(editTaxes || 0);
    if (!Number.isFinite(portfolioId) || !Number.isFinite(editingTransactionId ?? NaN)) return;

    if (!editTradeAt) {
      setEditTransactionError('Data/ora obbligatoria');
      return;
    }
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setEditTransactionError('Quantita non valida');
      return;
    }
    if (!Number.isFinite(price) || price < 0) {
      setEditTransactionError('Prezzo non valido');
      return;
    }
    if (!Number.isFinite(fees) || fees < 0 || !Number.isFinite(taxes) || taxes < 0) {
      setEditTransactionError('Fee/tasse non validi');
      return;
    }

    try {
      setEditTransactionError(null);
      setEditTransactionSaving(true);
      await updateTransaction(editingTransactionId as number, {
        trade_at: new Date(editTradeAt).toISOString(),
        quantity,
        price,
        fees,
        taxes,
        notes: editNotes.trim() || null,
      });
      await loadTransactions(portfolioId);
      setEditTransactionOpened(false);
      setFormSuccess('Transazione aggiornata');
    } catch (err) {
      setEditTransactionError(err instanceof Error ? err.message : 'Errore aggiornamento transazione');
    } finally {
      setEditTransactionSaving(false);
    }
  };

  const rows = allocations.map((item) => (
    <Table.Tr key={item.asset_id}>
      <Table.Td>
        <Text fw={500}>{item.symbol}</Text>
        <Text size="xs" c="dimmed">{item.name}</Text>
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{item.weight_pct.toFixed(2)}%</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>
        {portfolioTargetNotional != null
          ? formatMoney((portfolioTargetNotional * item.weight_pct) / 100, selectedPortfolio?.base_currency)
          : 'N/D'}
      </Table.Td>
      {!isMobile && (
        <Table.Td style={{ textAlign: 'right' }}>
          <ActionIcon color="red" variant="light" onClick={() => handleDeleteAllocation(item.asset_id)} aria-label={`Rimuovi ${item.symbol}`}>
            <IconTrash size={16} />
          </ActionIcon>
        </Table.Td>
      )}
    </Table.Tr>
  ));

  const discoverOptions = discoverItems.map((item) => ({
    value: item.key,
    label:
      `${item.symbol} - ${item.name ?? 'N/D'}${item.exchange ? ` (${item.exchange})` : ''}` +
      (item.source === 'db' ? ' [DB]' : ' [Provider]'),
  }));

  const txDiscoverOptions = txDiscoverItems.map((item) => ({
    value: item.key,
    label:
      `${item.symbol} - ${item.name ?? 'N/D'}${item.exchange ? ` (${item.exchange})` : ''}` +
      (item.source === 'db' ? ' [DB]' : ' [Provider]'),
  }));

  const filteredTransactions = useMemo(() => {
    const q = transactionFilterQuery.trim().toLowerCase();
    return transactions.filter((tx) => {
      const sideMatch = transactionFilterSide === 'all' || tx.side === transactionFilterSide;
      if (!sideMatch) return false;
      if (!q) return true;
      return (
        tx.symbol.toLowerCase().includes(q) ||
        (tx.asset_name ?? '').toLowerCase().includes(q) ||
        (tx.notes ?? '').toLowerCase().includes(q)
      );
    });
  }, [transactions, transactionFilterQuery, transactionFilterSide]);

  const sortedTransactions = useMemo(() => {
    const getDisplayedValue = (tx: TransactionListItem) => {
      const gross = tx.quantity * tx.price;
      return tx.side === 'buy'
        ? gross + (tx.fees ?? 0) + (tx.taxes ?? 0)
        : gross - (tx.fees ?? 0) - (tx.taxes ?? 0);
    };

    const copy = [...filteredTransactions];
    copy.sort((a, b) => {
      let av: string | number;
      let bv: string | number;
      switch (transactionSortKey) {
        case 'symbol':
          av = a.symbol.toLowerCase();
          bv = b.symbol.toLowerCase();
          break;
        case 'side':
          av = a.side;
          bv = b.side;
          break;
        case 'value':
          av = getDisplayedValue(a);
          bv = getDisplayedValue(b);
          break;
        case 'trade_at':
        default:
          av = new Date(a.trade_at).getTime();
          bv = new Date(b.trade_at).getTime();
          break;
      }
      if (av < bv) return transactionSortDir === 'asc' ? -1 : 1;
      if (av > bv) return transactionSortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [filteredTransactions, transactionSortKey, transactionSortDir]);

  const transactionTotals = useMemo(() => {
    const totalValue = sortedTransactions.reduce((sum, tx) => {
      const gross = tx.quantity * tx.price;
      const displayed = tx.side === 'buy'
        ? gross + (tx.fees ?? 0) + (tx.taxes ?? 0)
        : gross - (tx.fees ?? 0) - (tx.taxes ?? 0);
      return sum + displayed;
    }, 0);
    const currencies = Array.from(new Set(sortedTransactions.map((tx) => tx.trade_currency).filter(Boolean)));
    return {
      totalValue,
      currency: currencies.length === 1 ? currencies[0] : null,
      mixedCurrencies: currencies.length > 1,
    };
  }, [sortedTransactions]);

  const transactionRows = sortedTransactions.map((tx) => {
    const gross = tx.quantity * tx.price;
    const total = tx.side === 'buy' ? gross + (tx.fees ?? 0) + (tx.taxes ?? 0) : gross - (tx.fees ?? 0) - (tx.taxes ?? 0);
    return (
      <Table.Tr key={tx.id}>
        <Table.Td>{formatDateTime(tx.trade_at)}</Table.Td>
        <Table.Td>
          <Text fw={600} c={tx.side === 'buy' ? 'teal' : 'orange'}>
            {formatTransactionSideLabel(tx.side)}
          </Text>
        </Table.Td>
        <Table.Td>
          <Text fw={500}>{tx.symbol}</Text>
          {tx.asset_name ? <Text size="xs" c="dimmed">{tx.asset_name}</Text> : null}
        </Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">{tx.quantity}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">{formatMoney(tx.price, tx.trade_currency)}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="md">{formatMoney(tx.fees ?? 0, tx.trade_currency)}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }}>{formatMoney(total, tx.trade_currency)}</Table.Td>
        {!isMobile && (
          <Table.Td style={{ textAlign: 'right' }}>
            <Group gap={6} justify="flex-end" wrap="nowrap" style={{ minWidth: 74 }}>
              <ActionIcon
                color="blue"
                variant="light"
                onClick={() => openEditTransactionModal(tx)}
                aria-label={`Modifica transazione ${tx.id}`}
              >
                <IconEdit size={16} />
              </ActionIcon>
              <ActionIcon
                color="red"
                variant="light"
                onClick={() => openDeleteTransactionModal(tx)}
                loading={deletingTransactionId === tx.id}
                aria-label={`Elimina transazione ${tx.id}`}
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          </Table.Td>
        )}
      </Table.Tr>
    );
  });

  if (sortedTransactions.length > 0) {
    transactionRows.push(
      <Table.Tr key="transactions-total" style={{ fontWeight: 700, borderTop: '2px solid var(--mantine-color-dark-4)' }}>
        <Table.Td>
          <Text fw={700} size="sm">TOTALE</Text>
        </Table.Td>
        <Table.Td />
        <Table.Td />
        <Table.Td visibleFrom="sm" />
        <Table.Td visibleFrom="sm" />
        <Table.Td visibleFrom="md" />
        <Table.Td style={{ textAlign: 'right' }}>
          {transactionTotals.mixedCurrencies ? (
            <Text fw={700} size="sm" c="dimmed">Valute miste</Text>
          ) : (
            <Text fw={700} size="sm">
              {formatMoney(transactionTotals.totalValue, transactionTotals.currency ?? selectedPortfolio?.base_currency)}
            </Text>
          )}
        </Table.Td>
        {!isMobile && <Table.Td />}
      </Table.Tr>,
    );
  }

  const txGrossTotal = formatGrossTotal(txQuantity, txPrice);
  const editGrossTotal = formatGrossTotal(editQuantity, editPrice);

  return (
    <>
      {/* Header */}
      <Group justify="space-between" mb="md" wrap="wrap" gap="xs">
        <Title order={2} fw={700}>Il Mio Portafoglio</Title>
        {!isMobile && (
          <Button leftSection={<IconPlus size={16} />} variant="light" onClick={openCreatePortfolioModal}>
            Nuovo Portfolio
          </Button>
        )}
      </Group>

      {/* Selezione portfolio + menu azioni */}
      <Group mb="md" align="flex-end" gap="xs">
        <Select
          label="Portfolio attivo"
          placeholder={loadingPortfolios ? 'Caricamento...' : 'Seleziona portfolio'}
          data={portfolios.map((p) => ({ value: String(p.id), label: `${p.name} (#${p.id})` }))}
          value={selectedPortfolioId}
          onChange={setSelectedPortfolioId}
          disabled={loadingPortfolios || portfolios.length === 0}
          style={{ flex: 1, maxWidth: 420 }}
        />
        {!isMobile && (
          <Tooltip label="Azioni portfolio" disabled={!selectedPortfolioId}>
            <Menu shadow="md" width={200} position="bottom-end" disabled={!selectedPortfolioId}>
              <Menu.Target>
                <ActionIcon
                  variant="default"
                  size="lg"
                  disabled={!selectedPortfolioId}
                  aria-label="Azioni portfolio"
                >
                  <IconDotsVertical size={18} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconEdit size={14} />} onClick={openEditPortfolioModal}>
                  Modifica portfolio
                </Menu.Item>
                <Menu.Divider />
                <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => setPortfolioDeleteOpened(true)}>
                  Elimina portfolio
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Tooltip>
        )}
        {(loadingPortfolios || loadingData) && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>

      {/* Vista + azione contestuale */}
      <Group mb="md" justify="space-between" wrap="wrap" gap="xs">
        <SegmentedControl
          value={portfolioView}
          onChange={(value) => setPortfolioView((value as 'transactions' | 'target') ?? 'transactions')}
          size={isMobile ? 'md' : 'sm'}
          radius="xl"
          fullWidth={isMobile}
          style={isMobile ? { width: '100%' } : undefined}
          styles={isMobile ? {
            root: {
              padding: 4,
              background: 'var(--mantine-color-gray-1)',
            },
            control: {
              minWidth: 0,
              flex: 1,
            },
            label: {
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              minHeight: 36,
              paddingInline: 0,
            },
            indicator: {
              borderRadius: 999,
            },
          } : undefined}
          data={[
            {
              value: 'transactions',
              label: (
                <Group gap={0} wrap="nowrap" justify="center">
                  <IconArrowsExchange size={isMobile ? 20 : 14} />
                  {!isMobile && <span>Transazioni</span>}
                </Group>
              ),
            },
            {
              value: 'target',
              label: (
                <Group gap={0} wrap="nowrap" justify="center">
                  <IconTarget size={isMobile ? 20 : 14} />
                  {!isMobile && <span>Allocazione target</span>}
                </Group>
              ),
            },
          ]}
        />
        {portfolioView === 'transactions' && !isMobile && (
          <Button leftSection={<IconPlus size={16} />} onClick={openTransactionDrawer} disabled={!selectedPortfolioId}>
            Nuova Transazione
          </Button>
        )}
        {portfolioView === 'target' && !isMobile && (
          <Button variant="light" leftSection={<IconTarget size={16} />} onClick={openRebalancePreviewModal} disabled={!selectedPortfolioId}>
            Genera da target
          </Button>
        )}
      </Group>

      {error && <Alert color="red" mb="md">{error}</Alert>}
      {transactionsError && <Alert color="red" mb="md">{transactionsError}</Alert>}
      {formSuccess && <Alert color="teal" mb="md">{formSuccess}</Alert>}

      {portfolioView === 'target' && (
        <TargetAllocationSection
          allocationsCount={allocations.length}
          totalWeight={totalWeight}
          portfolioTargetNotionalLabel={formatMoney(portfolioTargetNotional, selectedPortfolio?.base_currency)}
          assignedTargetValueLabel={
            assignedTargetValue != null ? formatMoney(assignedTargetValue, selectedPortfolio?.base_currency) : null
          }
          selectedPortfolioId={selectedPortfolioId}
          rows={rows}
          hasRows={rows.length > 0}
          onOpenAddAssetWeight={openDrawer}
          showActions={!isMobile}
        />
      )}

      <TransactionsSection
        loading={loadingTransactions}
        filterQuery={transactionFilterQuery}
        onFilterQueryChange={setTransactionFilterQuery}
        filterSide={transactionFilterSide}
        onFilterSideChange={setTransactionFilterSide}
        sortKey={transactionSortKey}
        onSortKeyChange={(value) => setTransactionSortKey((value as 'trade_at' | 'symbol' | 'side' | 'value') ?? 'trade_at')}
        sortDir={transactionSortDir}
        onSortDirChange={(value) => setTransactionSortDir((value as 'asc' | 'desc') ?? 'desc')}
        rows={transactionRows}
        hasRows={transactionRows.length > 0}
        selectedPortfolioId={selectedPortfolioId}
        showActions={!isMobile}
      />

      <Modal
        opened={portfolioModalOpened}
        onClose={() => setPortfolioModalOpened(false)}
        title={portfolioModalMode === 'create' ? 'Nuovo Portfolio' : 'Modifica Portfolio'}
        centered
      >
        <Stack>
          {portfolioFormError && <Alert color="red">{portfolioFormError}</Alert>}
          <TextInput
            label="Nome"
            value={portfolioFormName}
            onChange={(event) => setPortfolioFormName(event.currentTarget.value)}
            placeholder="Es. Portafoglio ETF"
          />
          <TextInput
            label="Valuta Base"
            value={portfolioFormBaseCurrency}
            onChange={(event) => setPortfolioFormBaseCurrency(event.currentTarget.value.toUpperCase())}
            placeholder="EUR"
            maxLength={3}
          />
          <TextInput
            label="Timezone"
            value={portfolioFormTimezone}
            onChange={(event) => setPortfolioFormTimezone(event.currentTarget.value)}
            placeholder="Europe/Rome"
          />
          <NumberInput
            label={`Controvalore target (${portfolioFormBaseCurrency || 'EUR'})`}
            value={portfolioFormTargetNotional}
            onChange={setPortfolioFormTargetNotional}
            min={0}
            decimalScale={2}
            placeholder="Es. 100000"
            description="Opzionale. Usato per calcolare il controvalore target per asset dai pesi %."
          />
          <NumberInput
            label={`Cash disponibile (${portfolioFormBaseCurrency || 'EUR'})`}
            value={portfolioFormCashBalance}
            onChange={setPortfolioFormCashBalance}
            min={0}
            decimalScale={2}
            placeholder="Es. 5000"
            description="Liquidità non investita nel portfolio."
          />
          <Button onClick={handleSavePortfolio} loading={portfolioSaving}>
            {portfolioModalMode === 'create' ? 'Crea Portfolio' : 'Salva Modifiche'}
          </Button>
        </Stack>
      </Modal>

      <Modal
        opened={portfolioDeleteOpened}
        onClose={() => setPortfolioDeleteOpened(false)}
        title="Conferma eliminazione portfolio"
        centered
      >
        <Stack>
          <Text size="sm">
            Vuoi eliminare il portfolio {selectedPortfolio ? `"${selectedPortfolio.name}"` : ''}?
          </Text>
          <Text size="sm" c="dimmed">
            Verranno rimossi anche i pesi target e le eventuali transazioni collegate.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPortfolioDeleteOpened(false)} disabled={portfolioDeleting}>
              Annulla
            </Button>
            <Button color="red" onClick={handleDeletePortfolio} loading={portfolioDeleting}>
              Elimina Portfolio
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={rebalancePreviewOpened}
        onClose={() => setRebalancePreviewOpened(false)}
        title="Genera transazioni da target (Preview)"
        size="min(1100px, 95vw)"
        centered
      >
        <Stack>
          {rebalancePreviewError && <Alert color="red">{rebalancePreviewError}</Alert>}

          <Select
            label="Modalita"
            value={rebalanceMode}
            onChange={(value) => setRebalanceMode((value as 'buy_only' | 'rebalance' | 'sell_only') ?? 'buy_only')}
            data={[
              { value: 'buy_only', label: 'Solo acquisti (nuova liquidita)' },
              { value: 'rebalance', label: 'Ribilanciamento (buy + sell)' },
              { value: 'sell_only', label: 'Solo vendite' },
            ]}
          />

          <Group grow>
            <NumberInput
              label="N. max transazioni"
              value={rebalanceMaxTransactions}
              onChange={setRebalanceMaxTransactions}
              min={1}
              max={100}
            />
            <NumberInput
              label="Soglia minima ordine"
              value={rebalanceMinOrderValue}
              onChange={setRebalanceMinOrderValue}
              min={0}
              decimalScale={2}
            />
          </Group>

          {rebalanceMode === 'buy_only' && (
            <NumberInput
              label={`Importo da allocare (${selectedPortfolio?.base_currency ?? 'EUR'})`}
              value={rebalanceCashToAllocate}
              onChange={setRebalanceCashToAllocate}
              min={0}
              decimalScale={2}
            />
          )}

          <TextInput
            label="Data / ora operazioni (preview)"
            type="datetime-local"
            value={rebalanceTradeAt}
            onChange={(event) => setRebalanceTradeAt(event.currentTarget.value)}
          />

          <SegmentedControl
            value={rebalanceRounding}
            onChange={(value) => setRebalanceRounding((value as 'fractional' | 'integer') ?? 'fractional')}
            data={[
              { value: 'fractional', label: 'Quantita decimali' },
              { value: 'integer', label: 'Quantita intere' },
            ]}
          />

          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              Preview senza salvataggio. Le transazioni non vengono ancora create.
            </Text>
            <Button onClick={() => void handleLoadRebalancePreview()} loading={rebalancePreviewLoading}>
              Genera Preview
            </Button>
          </Group>

          {rebalancePreviewData && (
            <>
              {rebalancePreviewData.warnings.length > 0 && (
                <Alert color="yellow" title="Warning preview">
                  {rebalancePreviewData.warnings.slice(0, 10).map((w, index) => (
                    <Text key={`${w}-${index}`} size="sm">{w}</Text>
                  ))}
                </Alert>
              )}

              <Group grow>
                <Alert color="blue" variant="light" title="Riepilogo">
                  <Text size="sm">Generate: {rebalancePreviewData.summary.generated_count}</Text>
                  <Text size="sm">Saltate: {rebalancePreviewData.summary.skipped_count}</Text>
                </Alert>
                <Alert color="teal" variant="light" title="Totali">
                  <Text size="sm">
                    Buy: {formatMoney(rebalancePreviewData.summary.proposed_buy_total, rebalancePreviewData.base_currency)}
                  </Text>
                  <Text size="sm">
                    Sell: {formatMoney(rebalancePreviewData.summary.proposed_sell_total, rebalancePreviewData.base_currency)}
                  </Text>
                  <Text size="sm">
                    Residuo stimato: {formatMoney(rebalancePreviewData.summary.estimated_cash_residual, rebalancePreviewData.base_currency)}
                  </Text>
                </Alert>
              </Group>

              <Table.ScrollContainer minWidth={860}>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th style={{ width: 44 }}>
                        <Checkbox
                          aria-label="Seleziona tutte le proposte"
                          checked={rebalancePreviewData.items.length > 0 && rebalancePreviewData.items.every((item) => rebalanceSelectedRows[`${item.asset_id}-${item.side}`])}
                          indeterminate={
                            rebalancePreviewData.items.some((item) => rebalanceSelectedRows[`${item.asset_id}-${item.side}`]) &&
                            !rebalancePreviewData.items.every((item) => rebalanceSelectedRows[`${item.asset_id}-${item.side}`])
                          }
                          onChange={(event) => {
                            const checked = event.currentTarget.checked;
                            setRebalanceSelectedRows(
                              Object.fromEntries(rebalancePreviewData.items.map((item) => [`${item.asset_id}-${item.side}`, checked])),
                            );
                          }}
                        />
                      </Table.Th>
                      <Table.Th>Asset</Table.Th>
                      <Table.Th>Side</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Target %</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Attuale %</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Drift %</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Prezzo</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Qta</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Totale</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {rebalancePreviewData.items.length > 0 ? (
                      rebalancePreviewData.items.map((item) => (
                        <Table.Tr key={`${item.asset_id}-${item.side}`}>
                          <Table.Td>
                            <Checkbox
                              aria-label={`Seleziona ${item.symbol} ${item.side}`}
                              checked={Boolean(rebalanceSelectedRows[`${item.asset_id}-${item.side}`])}
                              onChange={(event) => {
                                const key = `${item.asset_id}-${item.side}`;
                                const checked = event.currentTarget.checked;
                                setRebalanceSelectedRows((prev) => ({ ...prev, [key]: checked }));
                              }}
                            />
                          </Table.Td>
                          <Table.Td>
                            <Text fw={600}>{item.symbol}</Text>
                            <Text size="xs" c="dimmed">{item.name}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text fw={600} c={item.side === 'buy' ? 'teal' : 'orange'}>
                              {item.side.toUpperCase()}
                            </Text>
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>{item.target_weight_pct.toFixed(2)}%</Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>{item.current_weight_pct.toFixed(2)}%</Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>
                            <Text c={item.drift_pct >= 0 ? 'orange' : 'teal'} fw={600} span>
                              {item.drift_pct > 0 ? '+' : ''}{item.drift_pct.toFixed(2)}%
                            </Text>
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>
                            {formatMoney(item.price, item.trade_currency)}
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>{item.quantity}</Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>
                            {formatMoney(item.gross_total, item.trade_currency)}
                          </Table.Td>
                        </Table.Tr>
                      ))
                    ) : (
                      <Table.Tr>
                        <Table.Td colSpan={9}>
                          <Text ta="center" c="dimmed">Nessuna proposta generata con i parametri selezionati</Text>
                        </Table.Td>
                      </Table.Tr>
                    )}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>

              <Group justify="space-between" align="flex-start">
                <Text size="sm" c="dimmed">
                  Seleziona le righe da creare e conferma. Le transazioni verranno salvate con fee/tasse = 0.
                </Text>
                <Button
                  color="teal"
                  onClick={() => void handleCommitRebalancePreview()}
                  loading={rebalanceCommitLoading}
                  disabled={!rebalancePreviewData.items.some((item) => rebalanceSelectedRows[`${item.asset_id}-${item.side}`])}
                >
                  Crea transazioni selezionate
                </Button>
              </Group>

              {rebalanceCommitResult && (
                <Alert color={rebalanceCommitResult.failed > 0 ? 'yellow' : 'teal'} title="Esito creazione transazioni">
                  <Text size="sm">
                    Richieste: {rebalanceCommitResult.requested} • Create: {rebalanceCommitResult.created} • Fallite: {rebalanceCommitResult.failed}
                  </Text>
                  {rebalanceCommitResult.errors.slice(0, 10).map((err, index) => (
                    <Text key={`${err}-${index}`} size="sm">{err}</Text>
                  ))}
                </Alert>
              )}
            </>
          )}
        </Stack>
      </Modal>

      <Drawer opened={drawerOpened} onClose={() => setDrawerOpened(false)} title="Aggiungi Asset al Portafoglio" position="right" size="md">
        <Stack>
          {formError && <Alert color="red">{formError}</Alert>}
          {formSuccess && <Alert color="teal">{formSuccess}</Alert>}

          <Select
            searchable
            label="Cerca asset (DB + provider)"
            placeholder="Scrivi simbolo, ISIN o nome (es. AAPL, IE00B3RBWM25, Apple)"
            searchValue={discoverQuery}
            onSearchChange={setDiscoverQuery}
            value={discoverSelectionKey}
            onChange={(value) => {
              void handleDiscoverSelection(value);
            }}
            data={discoverOptions}
            filter={({ options }) => options}
            nothingFoundMessage={discoverQuery.trim() ? 'Nessun risultato' : 'Inizia a digitare'}
            rightSection={discoverLoading || ensuringAsset ? <Loader size="xs" /> : null}
            clearable
          />

          <Text size="sm" c="dimmed">
            {resolvedAssetLabel ? `Asset selezionato: ${resolvedAssetLabel}` : 'Seleziona un asset dalla ricerca'}
          </Text>

          <NumberInput
            label="Peso target (%)"
            value={targetWeight}
            onChange={setTargetWeight}
            min={0}
            max={100}
            decimalScale={2}
            fixedDecimalScale
            suffix="%"
          />

          <Button onClick={handleSaveTargetWeight} loading={formSaving || ensuringAsset}>
            Aggiungi al Portafoglio
          </Button>
        </Stack>
      </Drawer>

      <Drawer
        opened={transactionDrawerOpened}
        onClose={() => setTransactionDrawerOpened(false)}
        title="Nuova Transazione"
        position="right"
        size="md"
      >
        <Stack>
          {txFormError && <Alert color="red">{txFormError}</Alert>}
          {txFormSuccess && <Alert color="teal">{txFormSuccess}</Alert>}

          <Select
            label="Tipo"
            data={[
              { value: 'buy', label: 'Acquisto' },
              { value: 'sell', label: 'Vendita' },
            ]}
            value={txSide}
            onChange={(value) => setTxSide((value as 'buy' | 'sell') ?? 'buy')}
          />

          <Select
            searchable
            label="Asset (DB + provider)"
            placeholder="Cerca simbolo, ISIN o nome"
            searchValue={txDiscoverQuery}
            onSearchChange={setTxDiscoverQuery}
            value={txDiscoverSelectionKey}
            onChange={(value) => {
              void handleTransactionDiscoverSelection(value);
            }}
            data={txDiscoverOptions}
            filter={({ options }) => options}
            nothingFoundMessage={txDiscoverQuery.trim() ? 'Nessun risultato' : 'Inizia a digitare'}
            rightSection={txDiscoverLoading || txEnsuringAsset ? <Loader size="xs" /> : null}
            clearable
          />

          <Text size="sm" c="dimmed">
            {txResolvedAssetLabel ? `Asset selezionato: ${txResolvedAssetLabel}` : 'Seleziona un asset dalla ricerca'}
          </Text>

          <TextInput
            label="Data / ora operazione"
            type="datetime-local"
            value={txTradeAt}
            onChange={(event) => setTxTradeAt(event.currentTarget.value)}
          />

          <NumberInput label="Quantita" value={txQuantity} onChange={setTxQuantity} min={0} decimalScale={8} />
          <NumberInput
            label="Prezzo"
            value={txPrice}
            onChange={setTxPrice}
            min={0}
            decimalScale={6}
            rightSection={txPriceLoading ? <Loader size="xs" /> : null}
            description={txPriceLoading ? 'Caricamento prezzo...' : undefined}
          />
          <TextInput
            label="Totale (Prezzo x Quantita)"
            value={txGrossTotal}
            readOnly
            placeholder="Calcolato automaticamente"
          />
          <NumberInput label="Fee" value={txFees} onChange={setTxFees} min={0} decimalScale={4} />
          <NumberInput label="Tasse" value={txTaxes} onChange={setTxTaxes} min={0} decimalScale={4} />
          <TextInput label="Note" value={txNotes} onChange={(event) => setTxNotes(event.currentTarget.value)} />

          <Button onClick={handleCreateTransaction} loading={txFormSaving || txEnsuringAsset}>
            Salva Transazione
          </Button>
        </Stack>
      </Drawer>

      <Modal
        opened={editTransactionOpened}
        onClose={() => setEditTransactionOpened(false)}
        title={`Modifica Transazione${editTransactionLabel ? ` - ${editTransactionLabel}` : ''}`}
        centered
      >
        <Stack>
          {editTransactionError && <Alert color="red">{editTransactionError}</Alert>}
          <TextInput
            label="Data / ora operazione"
            type="datetime-local"
            value={editTradeAt}
            onChange={(event) => setEditTradeAt(event.currentTarget.value)}
          />
          <NumberInput label="Quantita" value={editQuantity} onChange={setEditQuantity} min={0} decimalScale={8} />
          <NumberInput label="Prezzo" value={editPrice} onChange={setEditPrice} min={0} decimalScale={6} />
          <TextInput
            label="Totale (Prezzo x Quantita)"
            value={editGrossTotal}
            readOnly
            placeholder="Calcolato automaticamente"
          />
          <NumberInput label="Fee" value={editFees} onChange={setEditFees} min={0} decimalScale={4} />
          <NumberInput label="Tasse" value={editTaxes} onChange={setEditTaxes} min={0} decimalScale={4} />
          <TextInput label="Note" value={editNotes} onChange={(event) => setEditNotes(event.currentTarget.value)} />
          <Button onClick={handleUpdateTransaction} loading={editTransactionSaving}>
            Salva Modifiche
          </Button>
        </Stack>
      </Modal>

      <Modal
        opened={transactionDeleteOpened}
        onClose={() => setTransactionDeleteOpened(false)}
        title="Conferma eliminazione transazione"
        centered
      >
        <Stack>
          <Text size="sm">
            Vuoi eliminare la transazione {transactionLabelToDelete ? `"${transactionLabelToDelete}"` : ''}?
          </Text>
          <Text size="sm" c="dimmed">
            L'operazione aggiornera' automaticamente storico, posizioni e dashboard.
          </Text>
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => setTransactionDeleteOpened(false)}
              disabled={deletingTransactionId != null}
            >
              Annulla
            </Button>
            <Button
              color="red"
              onClick={() => void confirmDeleteTransaction()}
              loading={deletingTransactionId === transactionIdToDelete}
            >
              Elimina Transazione
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
