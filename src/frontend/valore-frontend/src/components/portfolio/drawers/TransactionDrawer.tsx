import { useState, useRef, useEffect } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Loader,
  NumberInput,
  Select,
  Stack,
  TextInput,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { createTransaction } from '../../../services/api';
import type { Portfolio } from '../../../services/api';
import { formatGrossTotal } from '../../dashboard/formatters';
import { AssetDiscoverSelect } from '../AssetDiscoverSelect';
import { STORAGE_KEYS } from '../../dashboard/constants';
import { useSwipeToClose } from '../../../hooks/useSwipeToClose';

interface TransactionDrawerProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number | null;
  selectedPortfolio: Portfolio | null;
  onTransactionCreated: () => void;
}

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

export function TransactionDrawer({
  opened,
  onClose,
  portfolioId,
  selectedPortfolio,
  onTransactionCreated,
}: TransactionDrawerProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const swipeHandlers = useSwipeToClose(onClose, { enabled: Boolean(isMobile) });
  const firstInputRef = useRef<HTMLInputElement>(null);

  // Auto-focus the first interactive field when drawer opens on mobile
  useEffect(() => {
    if (opened && isMobile && firstInputRef.current) {
      // Small delay to let the drawer animation finish
      const timer = setTimeout(() => firstInputRef.current?.focus(), 350);
      return () => clearTimeout(timer);
    }
  }, [opened, isMobile]);

  const [resolvedAssetId, setResolvedAssetId] = useState<number | null>(null);
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [tradeAt, setTradeAt] = useState(() => currentDateTimeLocalValue());
  const [quantity, setQuantity] = useState<number | string>('');
  const [price, setPrice] = useState<number | string>('');
  const [priceLoading] = useState(false);
  const [priceHint, setPriceHint] = useState<string | null>(null);
  const [fees, setFees] = useState<number | string>(() => getDefaultBrokerFee());
  const [taxes, setTaxes] = useState<number | string>(0);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const grossTotal = formatGrossTotal(quantity, price);

  const handleSave = async () => {
    const qty = typeof quantity === 'number' ? quantity : Number(quantity);
    const prc = typeof price === 'number' ? price : Number(price);
    const feesNum = typeof fees === 'number' ? fees : Number(fees || 0);
    const taxesNum = typeof taxes === 'number' ? taxes : Number(taxes || 0);

    setError(null);
    setSuccess(null);

    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setError('Seleziona un portfolio valido');
      return;
    }
    if (!resolvedAssetId) {
      setError('Seleziona un asset');
      return;
    }
    if (!tradeAt) {
      setError('Data/ora operazione obbligatoria');
      return;
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      setError('Quantita non valida');
      return;
    }
    if (!Number.isFinite(prc) || prc < 0) {
      setError('Prezzo non valido');
      return;
    }
    if (!Number.isFinite(feesNum) || feesNum < 0 || !Number.isFinite(taxesNum) || taxesNum < 0) {
      setError('Fee/tasse non validi');
      return;
    }

    try {
      setSaving(true);
      await createTransaction({
        portfolio_id: portfolioId,
        asset_id: resolvedAssetId,
        side,
        trade_at: new Date(tradeAt).toISOString(),
        quantity: qty,
        price: prc,
        fees: feesNum,
        taxes: taxesNum,
        trade_currency: selectedPortfolio?.base_currency ?? 'EUR',
        notes: notes.trim() || null,
      });
      onClose();
      onTransactionCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore salvataggio transazione');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      title="Nuova Transazione"
      position={isMobile ? 'bottom' : 'right'}
      size={isMobile ? '100%' : 'md'}
      radius={isMobile ? '24px 24px 0 0' : undefined}
      styles={{
        content: { paddingBottom: 'var(--safe-area-bottom)' },
        body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
      }}
      onTouchStart={isMobile ? swipeHandlers.onTouchStart : undefined}
      onTouchEnd={isMobile ? swipeHandlers.onTouchEnd : undefined}
    >
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        {success && <Alert color="teal">{success}</Alert>}

        <Select
          label="Tipo"
          data={[
            { value: 'buy', label: 'Acquisto' },
            { value: 'sell', label: 'Vendita' },
          ]}
          value={side}
          onChange={(value) => setSide((value as 'buy' | 'sell') ?? 'buy')}
        />

        <AssetDiscoverSelect
          active={opened}
          portfolioId={portfolioId}
          label="Asset (DB + provider)"
          placeholder="Cerca simbolo, ISIN o nome"
          fetchPrice
          onAssetResolved={(result) => {
            setResolvedAssetId(result.assetId);
            if (result.created) {
              setSuccess(`Asset ${result.label} creato e selezionato.`);
            }
          }}
          onClear={() => {
            setResolvedAssetId(null);
            setPrice('');
            setPriceHint(null);
          }}
          onError={(msg) => setError(msg)}
          onPriceFetched={(fetchedPrice, hint) => {
            setPrice(fetchedPrice);
            setPriceHint(hint);
          }}
        />

        <TextInput
          label="Data / ora operazione"
          type="datetime-local"
          value={tradeAt}
          onChange={(event) => setTradeAt(event.currentTarget.value)}
        />

        <NumberInput label="Quantita" value={quantity} onChange={setQuantity} min={0} decimalScale={8} />
        <NumberInput
          label="Prezzo"
          value={price}
          onChange={setPrice}
          min={0}
          decimalScale={6}
          rightSection={priceLoading ? <Loader size="xs" /> : null}
          description={priceLoading ? 'Caricamento prezzo...' : (priceHint ?? undefined)}
        />
        <TextInput
          label="Totale (Prezzo x Quantita)"
          value={grossTotal}
          readOnly
          placeholder="Calcolato automaticamente"
        />
        <NumberInput label="Fee" value={fees} onChange={setFees} min={0} decimalScale={4} />
        <NumberInput label="Tasse" value={taxes} onChange={setTaxes} min={0} decimalScale={4} />
        <TextInput label="Note" value={notes} onChange={(event) => setNotes(event.currentTarget.value)} />

        <Button onClick={handleSave} loading={saving}>
          Salva Transazione
        </Button>
      </Stack>
    </Drawer>
  );
}
