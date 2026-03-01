import { useEffect, useState } from 'react';
import {
  Button,
  Checkbox,
  Drawer,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import {
  createPacRule,
  updatePacRule,
  type PacRuleCreateInput,
  type PacRuleRead,
  type PacRuleUpdateInput,
} from '../../services/api';

interface PacRuleDrawerProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number;
  baseCurrency: string;
  editingRule?: PacRuleRead | null;
  selectedAssetId?: number | null;
  selectedAssetSymbol?: string | null;
  onSaved?: () => void;
}

const DAY_OF_WEEK_OPTIONS = [
  { value: '0', label: 'Lunedì' },
  { value: '1', label: 'Martedì' },
  { value: '2', label: 'Mercoledì' },
  { value: '3', label: 'Giovedì' },
  { value: '4', label: 'Venerdì' },
  { value: '5', label: 'Sabato' },
  { value: '6', label: 'Domenica' },
];

export function PacRuleDrawer({
  opened,
  onClose,
  portfolioId,
  baseCurrency,
  editingRule,
  selectedAssetId,
  selectedAssetSymbol,
  onSaved,
}: PacRuleDrawerProps) {
  const [mode, setMode] = useState<'amount' | 'quantity'>('amount');
  const [amount, setAmount] = useState<number | string>('');
  const [quantity, setQuantity] = useState<number | string>('');
  const [frequency, setFrequency] = useState<string>('monthly');
  const [dayOfMonth, setDayOfMonth] = useState<number | string>(1);
  const [dayOfWeek, setDayOfWeek] = useState<string>('0');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [autoExecute, setAutoExecute] = useState(false);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [assetSymbol, setAssetSymbol] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editingRule) {
      setMode(editingRule.mode);
      setAmount(editingRule.amount ?? '');
      setQuantity(editingRule.quantity ?? '');
      setFrequency(editingRule.frequency);
      setDayOfMonth(editingRule.day_of_month ?? 1);
      setDayOfWeek(String(editingRule.day_of_week ?? 0));
      setStartDate(editingRule.start_date);
      setEndDate(editingRule.end_date ?? '');
      setAutoExecute(editingRule.auto_execute);
      setAssetId(editingRule.asset_id);
      setAssetSymbol(editingRule.symbol ?? '');
    } else {
      setMode('amount');
      setAmount('');
      setQuantity('');
      setFrequency('monthly');
      setDayOfMonth(1);
      setDayOfWeek('0');
      setStartDate(new Date().toISOString().split('T')[0]);
      setEndDate('');
      setAutoExecute(false);
      setAssetId(selectedAssetId ?? null);
      setAssetSymbol(selectedAssetSymbol ?? '');
    }
  }, [editingRule, opened, selectedAssetId, selectedAssetSymbol]);

  const handleSubmit = async () => {
    if (!assetId) {
      setError('Seleziona un asset');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);

      if (editingRule) {
        const payload: PacRuleUpdateInput = {
          mode,
          amount: mode === 'amount' ? Number(amount) : undefined,
          quantity: mode === 'quantity' ? Number(quantity) : undefined,
          frequency: frequency as PacRuleUpdateInput['frequency'],
          day_of_month: frequency === 'monthly' ? Number(dayOfMonth) : undefined,
          day_of_week: frequency !== 'monthly' ? Number(dayOfWeek) : undefined,
          end_date: endDate || undefined,
          auto_execute: autoExecute,
        };
        await updatePacRule(editingRule.id, payload);
      } else {
        const payload: PacRuleCreateInput = {
          portfolio_id: portfolioId,
          asset_id: assetId,
          mode,
          amount: mode === 'amount' ? Number(amount) : undefined,
          quantity: mode === 'quantity' ? Number(quantity) : undefined,
          frequency: frequency as PacRuleCreateInput['frequency'],
          day_of_month: frequency === 'monthly' ? Number(dayOfMonth) : undefined,
          day_of_week: frequency !== 'monthly' ? Number(dayOfWeek) : undefined,
          start_date: startDate,
          end_date: endDate || undefined,
          auto_execute: autoExecute,
        };
        await createPacRule(portfolioId, payload);
      }

      onClose();
      onSaved?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      title={editingRule ? 'Modifica PAC' : 'Nuovo Piano di Accumulo'}
      position="right"
      size="md"
    >
      <Stack>
        <TextInput
          label="Asset"
          value={assetSymbol}
          disabled
          description={editingRule ? 'Non modificabile' : 'Seleziona prima un asset dalla lista'}
        />

        <Select
          label="Modalità"
          data={[
            { value: 'amount', label: 'Importo fisso' },
            { value: 'quantity', label: 'Quantità fissa' },
          ]}
          value={mode}
          onChange={(v) => setMode((v as 'amount' | 'quantity') ?? 'amount')}
        />

        {mode === 'amount' && (
          <NumberInput
            label={`Importo (${baseCurrency})`}
            placeholder="100.00"
            min={0.01}
            decimalScale={2}
            value={amount}
            onChange={setAmount}
          />
        )}

        {mode === 'quantity' && (
          <NumberInput
            label="Quantità"
            placeholder="1.0000"
            min={0.0001}
            decimalScale={4}
            value={quantity}
            onChange={setQuantity}
          />
        )}

        <Select
          label="Frequenza"
          data={[
            { value: 'weekly', label: 'Settimanale' },
            { value: 'biweekly', label: 'Bisettimanale' },
            { value: 'monthly', label: 'Mensile' },
          ]}
          value={frequency}
          onChange={(v) => setFrequency(v ?? 'monthly')}
        />

        {frequency === 'monthly' && (
          <NumberInput
            label="Giorno del mese"
            min={1}
            max={28}
            value={dayOfMonth}
            onChange={setDayOfMonth}
          />
        )}

        {(frequency === 'weekly' || frequency === 'biweekly') && (
          <Select
            label="Giorno della settimana"
            data={DAY_OF_WEEK_OPTIONS}
            value={dayOfWeek}
            onChange={(v) => setDayOfWeek(v ?? '0')}
          />
        )}

        {!editingRule && (
          <TextInput
            label="Data inizio"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.currentTarget.value)}
          />
        )}

        <TextInput
          label="Data fine (opzionale)"
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.currentTarget.value)}
        />

        <Checkbox
          label="Esecuzione automatica"
          checked={autoExecute}
          onChange={(e) => setAutoExecute(e.currentTarget.checked)}
          description="Se abilitato, le esecuzioni verranno create automaticamente"
        />

        {error && <Text c="red" size="sm">{error}</Text>}

        <Button onClick={handleSubmit} loading={submitting}>
          {editingRule ? 'Salva Modifiche' : 'Crea PAC'}
        </Button>
      </Stack>
    </Drawer>
  );
}
