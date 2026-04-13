import { useEffect, useState } from 'react';
import { Loader, Select, Text } from '@mantine/core';
import { discoverAssets, ensureAsset, getAssetLatestQuote } from '../../services/api';
import type { AssetDiscoverItem } from '../../services/api';
import { formatPriceSourceLabel, formatProviderWarning } from '../../services/dataQuality';

interface AssetDiscoverSelectProps {
  /** Whether the parent container (drawer/modal) is open — controls debounced search */
  active: boolean;
  /** Portfolio id used for ensureAsset context */
  portfolioId: number | null;
  /** Label shown above the select */
  label?: string;
  /** Placeholder text */
  placeholder?: string;
  /** Whether to auto-fetch latest price on selection */
  fetchPrice?: boolean;
  /** Called when an asset is resolved (selected + ensured) */
  onAssetResolved: (result: AssetResolveResult) => void;
  /** Called when selection is cleared */
  onClear?: () => void;
  /** Called on error */
  onError?: (message: string) => void;
  /** Called when price is fetched (only if fetchPrice=true) */
  onPriceFetched?: (price: number, hint: string | null) => void;
}

export interface AssetResolveResult {
  assetId: number;
  label: string;
  created: boolean;
}

export function AssetDiscoverSelect({
  active,
  portfolioId,
  label = 'Cerca asset (DB + provider)',
  placeholder = 'Scrivi simbolo, ISIN o nome (es. AAPL, IE00B3RBWM25, Apple)',
  fetchPrice = false,
  onAssetResolved,
  onClear,
  onError,
  onPriceFetched,
}: AssetDiscoverSelectProps) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<AssetDiscoverItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectionKey, setSelectionKey] = useState<string | null>(null);
  const [ensuring, setEnsuring] = useState(false);
  const [resolvedLabel, setResolvedLabel] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    const q = query.trim();
    if (!q) {
      setItems([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      discoverAssets(q)
        .then((result) => {
          if (!cancelled) setItems(result);
        })
        .catch(() => {
          if (!cancelled) setItems([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, active]);

  const options = items.map((item) => ({
    value: item.key,
    label:
      `${item.symbol} - ${item.name ?? 'N/D'}${item.exchange ? ` (${item.exchange})` : ''}` +
      (item.source === 'db' ? ' [DB]' : ' [Provider]'),
  }));

  const doFetchPrice = async (assetId: number) => {
    if (!fetchPrice || !onPriceFetched) return;
    try {
      const quote = await getAssetLatestQuote(assetId);
      const hint =
        formatProviderWarning(quote.warning)
          ?? (quote.stale || quote.is_fallback
            ? `Prezzo automatico non realtime (${formatPriceSourceLabel(quote.quote_source) ?? 'fallback'})`
            : null);
      onPriceFetched(quote.price, hint);
    } catch {
      // price not available — user enters it manually
    }
  };

  const handleSelection = async (value: string | null) => {
    setSelectionKey(value);
    setResolvedLabel(null);

    if (!value) {
      onClear?.();
      return;
    }

    const selected = items.find((item) => item.key === value);
    if (!selected) return;

    const assetLabel = `${selected.symbol} - ${selected.name ?? 'N/D'}${selected.exchange ? ` (${selected.exchange})` : ''}`;

    if (selected.source === 'db' && selected.asset_id) {
      setResolvedLabel(assetLabel);
      onAssetResolved({ assetId: selected.asset_id, label: assetLabel, created: false });
      void doFetchPrice(selected.asset_id);
      return;
    }

    try {
      setEnsuring(true);
      const ensured = await ensureAsset({
        source: selected.source,
        asset_id: selected.asset_id,
        symbol: selected.symbol,
        name: selected.name,
        exchange: selected.exchange,
        provider: selected.provider ?? 'yfinance',
        provider_symbol: selected.provider_symbol ?? selected.symbol,
        portfolio_id: portfolioId != null && Number.isFinite(portfolioId) ? portfolioId : undefined,
      });
      setResolvedLabel(assetLabel);
      onAssetResolved({ assetId: ensured.asset_id, label: assetLabel, created: ensured.created });
      void doFetchPrice(ensured.asset_id);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Errore nella risoluzione asset');
    } finally {
      setEnsuring(false);
    }
  };

  return (
    <>
      <Select
        searchable
        label={label}
        placeholder={placeholder}
        searchValue={query}
        onSearchChange={setQuery}
        value={selectionKey}
        onChange={(value) => { void handleSelection(value); }}
        data={options}
        filter={({ options: opts }) => opts}
        nothingFoundMessage={query.trim() ? 'Nessun risultato' : 'Inizia a digitare'}
        rightSection={loading || ensuring ? <Loader size="xs" /> : null}
        clearable
      />
      <Text size="sm" c="dimmed">
        {resolvedLabel ? `Asset selezionato: ${resolvedLabel}` : 'Seleziona un asset dalla ricerca'}
      </Text>
    </>
  );
}
