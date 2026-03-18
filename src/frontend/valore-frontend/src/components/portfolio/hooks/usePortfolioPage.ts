import { useEffect, useMemo, useState } from 'react';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import {
  deleteTransaction,
  createPortfolio,
  clonePortfolio,
  deletePortfolio,
  deletePortfolioTargetAllocation,
  getAdminPortfolios,
  getPortfolioTargetAllocation,
  getPortfolioTransactions,
  updateTransaction,
  updatePortfolio,
  getCopilotStatus,
} from '../../../services/api';
import type {
  PacRuleRead,
  PortfolioTargetAllocationItem,
  TransactionListItem,
} from '../../../services/api';
import { STORAGE_KEYS } from '../../dashboard/constants';
import { formatNum, formatTransactionSideLabel } from '../../dashboard/formatters';
import { ENABLE_TARGET_ALLOCATION } from '../../../features';
import { useRebalance } from './useRebalance';

// Re-export shared formatters for consumers
export { formatMoneyOrNA as formatMoney, formatDateTime, formatTransactionSideLabel, formatGrossTotal, getTransactionSideColor } from '../../dashboard/formatters';

const toLocalDateTimeInput = (value: string) => {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '';
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
};

export function usePortfolioPage() {
  const isMobile = useMediaQuery('(max-width: 48em)');

  // --- Portfolio state ---
  const [portfolios, setPortfolios] = useState<import('../../../services/api').Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });
  const [allocations, setAllocations] = useState<PortfolioTargetAllocationItem[]>([]);
  const [loadingPortfolios, setLoadingPortfolios] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [portfolioView, setPortfolioView] = useState<'transactions' | 'target'>('transactions');

  // --- Portfolio modal state ---
  const [portfolioModalOpened, setPortfolioModalOpened] = useState(false);
  const [portfolioModalMode, setPortfolioModalMode] = useState<'create' | 'edit'>('create');
  const [portfolioDeleteOpened, setPortfolioDeleteOpened] = useState(false);
  const [portfolioCloneOpened, setPortfolioCloneOpened] = useState(false);
  const [portfolioCloneName, setPortfolioCloneName] = useState('');
  const [portfolioCloneError, setPortfolioCloneError] = useState<string | null>(null);
  const [portfolioCloning, setPortfolioCloning] = useState(false);
  const [portfolioSaving, setPortfolioSaving] = useState(false);
  const [portfolioDeleting, setPortfolioDeleting] = useState(false);
  const [portfolioFormError, setPortfolioFormError] = useState<string | null>(null);
  const [portfolioFormName, setPortfolioFormName] = useState('');
  const [portfolioFormBaseCurrency, setPortfolioFormBaseCurrency] = useState('EUR');
  const [portfolioFormTimezone, setPortfolioFormTimezone] = useState('Europe/Rome');
  const [portfolioFormTargetNotional, setPortfolioFormTargetNotional] = useState<number | string>('');


  // --- Transaction state ---
  const [transactions, setTransactions] = useState<TransactionListItem[]>([]);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [loadingTransactions, setLoadingTransactions] = useState(false);
  const [deletingTransactionId, setDeletingTransactionId] = useState<number | null>(null);
  const [transactionDeleteOpened, setTransactionDeleteOpened] = useState(false);
  const [transactionIdToDelete, setTransactionIdToDelete] = useState<number | null>(null);
  const [transactionLabelToDelete, setTransactionLabelToDelete] = useState<string | null>(null);
  const [transactionFilterQuery, setTransactionFilterQuery] = useState('');
  const [transactionFilterSide, setTransactionFilterSide] = useState<string>('all');
  const [transactionSortKey, setTransactionSortKey] = useState<'trade_at' | 'symbol' | 'side' | 'value'>('trade_at');
  const [transactionSortDir, setTransactionSortDir] = useState<'asc' | 'desc'>('desc');

  // --- Edit transaction modal ---
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

  // --- Drawer/modal toggles ---
  const [drawerOpened, setDrawerOpened] = useState(false);
  const [transactionDrawerOpened, setTransactionDrawerOpened] = useState(false);
  const [csvImportOpened, setCsvImportOpened] = useState(false);
  const [targetCsvImportOpened, setTargetCsvImportOpened] = useState(false);
  const [pacDrawerOpened, setPacDrawerOpened] = useState(false);
  const [mobileActionSheetOpened, setMobileActionSheetOpened] = useState(false);
  const [editingPacRule, setEditingPacRule] = useState<PacRuleRead | null>(null);
  const [pacRefreshTrigger, setPacRefreshTrigger] = useState(0);

  // --- Copilot ---
  const [copilotOpened, { open: openCopilot, close: closeCopilot }] = useDisclosure(false);
  const [copilotAvailable, setCopilotAvailable] = useState(false);

  useEffect(() => {
    getCopilotStatus().then((s) => setCopilotAvailable(s.available)).catch(() => {});
  }, []);

  // --- Computed ---
  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const totalWeight = useMemo(
    () => allocations.reduce((sum, item) => sum + item.weight_pct, 0),
    [allocations],
  );
  const portfolioTargetNotional = selectedPortfolio?.target_notional ?? null;
  const assignedTargetValue = useMemo(
    () => (portfolioTargetNotional != null ? (portfolioTargetNotional * totalWeight) / 100 : null),
    [portfolioTargetNotional, totalWeight],
  );

  // --- Data loading ---

  const loadTargetAllocation = async (portfolioId: number) => {
    if (!ENABLE_TARGET_ALLOCATION) {
      setAllocations([]);
      return [];
    }
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
    window.dispatchEvent(new CustomEvent('valore365:portfolios-changed', { detail: { count: items.length } }));
    setSelectedPortfolioId((prev) => {
      const storedSelectedId = typeof window !== 'undefined'
        ? window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId)
        : null;
      const candidate = preferredSelectedId ?? prev ?? storedSelectedId;
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

  // --- Rebalance (delegated) ---
  const rebalance = useRebalance(selectedPortfolioId, isMobile, loadTransactions, setFormSuccess);

  // --- Effects ---

  useEffect(() => {
    let active = true;
    setLoadingPortfolios(true);
    setError(null);

    loadPortfolios()
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento portafogli');
      })
      .finally(() => {
        if (active) setLoadingPortfolios(false);
      });

    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (isMobile && rebalance.previewOpened) {
      rebalance.setPreviewOpened(false);
    }
  }, [isMobile, rebalance.previewOpened]);

  useEffect(() => {
    if (!ENABLE_TARGET_ALLOCATION) {
      setAllocations([]);
      return;
    }
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

    return () => { active = false; };
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!ENABLE_TARGET_ALLOCATION && portfolioView === 'target') {
      setPortfolioView('transactions');
    }
  }, [portfolioView]);

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

    return () => { active = false; };
  }, [selectedPortfolioId]);

  // --- Filtered & sorted transactions ---

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

  // --- Open/close helpers ---

  const openCreatePortfolioModal = () => {
    setPortfolioModalMode('create');
    setPortfolioFormName('');
    setPortfolioFormBaseCurrency('EUR');
    setPortfolioFormTimezone('Europe/Rome');
    setPortfolioFormTargetNotional('');
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
    setPortfolioFormError(null);
    setPortfolioModalOpened(true);
  };

  const openClonePortfolioModal = () => {
    if (!selectedPortfolio) return;
    setPortfolioCloneName(`${selectedPortfolio.name} (Copia)`);
    setPortfolioCloneError(null);
    setPortfolioCloneOpened(true);
  };

  const openDeleteTransactionModal = (tx: TransactionListItem) => {
    setTransactionIdToDelete(tx.id);
    setTransactionLabelToDelete(`${formatTransactionSideLabel(tx.side)} ${tx.symbol} (${formatNum(tx.quantity, 4)})`);
    setTransactionDeleteOpened(true);
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

  // --- CRUD handlers ---

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
    if (!name) { setPortfolioFormError('Nome portfolio obbligatorio'); return; }
    if (!/^[A-Z]{3}$/.test(baseCurrency)) { setPortfolioFormError('Valuta base non valida (es. EUR)'); return; }
    if (!timezone) { setPortfolioFormError('Timezone obbligatoria'); return; }
    if (normalizedTargetNotional !== null && (!Number.isFinite(normalizedTargetNotional) || normalizedTargetNotional < 0)) {
      setPortfolioFormError('Controvalore target non valido'); return;
    }
    try {
      setPortfolioSaving(true);
      if (portfolioModalMode === 'create') {
        const created = await createPortfolio({ name, base_currency: baseCurrency, timezone, target_notional: normalizedTargetNotional });
        await loadPortfolios(String(created.id));
        setFormSuccess(`Portfolio "${created.name}" creato`);
      } else {
        const portfolioId = Number(selectedPortfolioId);
        if (!Number.isFinite(portfolioId)) { setPortfolioFormError('Seleziona un portfolio valido'); return; }
        const updated = await updatePortfolio(portfolioId, { name, base_currency: baseCurrency, timezone, target_notional: normalizedTargetNotional });
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

  const handleClonePortfolio = async () => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;
    const cloneName = portfolioCloneName.trim();
    if (!cloneName) { setPortfolioCloneError('Nome portfolio clone obbligatorio'); return; }
    try {
      setPortfolioCloneError(null);
      setPortfolioCloning(true);
      const result = await clonePortfolio(portfolioId, { name: cloneName });
      await loadPortfolios(String(result.portfolio.id));
      setPortfolioCloneOpened(false);
      setFormSuccess(`Portfolio "${result.portfolio.name}" clonato (${result.target_allocations_copied} allocazioni target)`);
    } catch (err) {
      setPortfolioCloneError(err instanceof Error ? err.message : 'Errore clonazione portfolio');
    } finally {
      setPortfolioCloning(false);
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

  const confirmDeleteTransaction = async () => {
    if (!transactionIdToDelete) return;
    await handleDeleteTransaction(transactionIdToDelete);
    setTransactionDeleteOpened(false);
    setTransactionIdToDelete(null);
    setTransactionLabelToDelete(null);
  };

  const handleUpdateTransaction = async () => {
    const portfolioId = Number(selectedPortfolioId);
    const quantity = typeof editQuantity === 'number' ? editQuantity : Number(editQuantity);
    const price = typeof editPrice === 'number' ? editPrice : Number(editPrice);
    const fees = typeof editFees === 'number' ? editFees : Number(editFees || 0);
    const taxes = typeof editTaxes === 'number' ? editTaxes : Number(editTaxes || 0);
    if (!Number.isFinite(portfolioId) || !Number.isFinite(editingTransactionId ?? NaN)) return;
    if (!editTradeAt) { setEditTransactionError('Data/ora obbligatoria'); return; }
    if (!Number.isFinite(quantity) || quantity <= 0) { setEditTransactionError('Quantita non valida'); return; }
    if (!Number.isFinite(price) || price < 0) { setEditTransactionError('Prezzo non valido'); return; }
    if (!Number.isFinite(fees) || fees < 0 || !Number.isFinite(taxes) || taxes < 0) { setEditTransactionError('Fee/tasse non validi'); return; }

    try {
      setEditTransactionError(null);
      setEditTransactionSaving(true);
      await updateTransaction(editingTransactionId as number, {
        trade_at: new Date(editTradeAt).toISOString(),
        quantity, price, fees, taxes,
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

  return {
    isMobile,
    portfolios, selectedPortfolioId, setSelectedPortfolioId, selectedPortfolio,
    loadingPortfolios, loadingData, error, transactionsError, formSuccess, setFormSuccess,
    portfolioView, setPortfolioView,
    // Portfolio modal
    portfolioModalOpened, setPortfolioModalOpened, portfolioModalMode,
    portfolioFormError, portfolioFormName, setPortfolioFormName,
    portfolioFormBaseCurrency, setPortfolioFormBaseCurrency,
    portfolioFormTimezone, setPortfolioFormTimezone,
    portfolioFormTargetNotional, setPortfolioFormTargetNotional,
    portfolioSaving, handleSavePortfolio, openCreatePortfolioModal, openEditPortfolioModal,
    // Clone
    portfolioCloneOpened, setPortfolioCloneOpened,
    portfolioCloneName, setPortfolioCloneName, portfolioCloneError, portfolioCloning, handleClonePortfolio, openClonePortfolioModal,
    // Delete
    portfolioDeleteOpened, setPortfolioDeleteOpened, portfolioDeleting, handleDeletePortfolio,
    // Allocations
    allocations, totalWeight, portfolioTargetNotional, assignedTargetValue, handleDeleteAllocation,
    // Target allocation drawer
    drawerOpened, setDrawerOpened,
    // Transactions
    sortedTransactions, loadingTransactions,
    transactionFilterQuery, setTransactionFilterQuery,
    transactionFilterSide, setTransactionFilterSide,
    transactionSortKey, setTransactionSortKey,
    transactionSortDir, setTransactionSortDir,
    transactionTotals, deletingTransactionId,
    // Transaction drawer
    transactionDrawerOpened, setTransactionDrawerOpened,
    // Transaction edit modal
    editTransactionOpened, setEditTransactionOpened,
    editTransactionLabel, editTransactionError,
    editTradeAt, setEditTradeAt,
    editQuantity, setEditQuantity, editPrice, setEditPrice,
    editFees, setEditFees, editTaxes, setEditTaxes,
    editNotes, setEditNotes,
    editTransactionSaving, handleUpdateTransaction, openEditTransactionModal,
    // Transaction delete modal
    transactionDeleteOpened, setTransactionDeleteOpened,
    transactionLabelToDelete, transactionIdToDelete,
    confirmDeleteTransaction, openDeleteTransactionModal,
    // Rebalance (composed)
    rebalance,
    // CSV Import
    csvImportOpened, setCsvImportOpened, targetCsvImportOpened, setTargetCsvImportOpened,
    // PAC
    pacDrawerOpened, setPacDrawerOpened, editingPacRule, setEditingPacRule, pacRefreshTrigger, setPacRefreshTrigger,
    // Mobile
    mobileActionSheetOpened, setMobileActionSheetOpened,
    // Copilot
    copilotOpened, openCopilot, closeCopilot, copilotAvailable,
    // Data loaders
    loadPortfolios, loadTransactions, loadTargetAllocation,
  };
}
