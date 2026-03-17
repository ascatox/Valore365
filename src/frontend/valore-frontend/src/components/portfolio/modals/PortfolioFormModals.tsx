import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { IconCopy } from '@tabler/icons-react';
import type { Portfolio } from '../../../services/api';
import { formatGrossTotal } from '../../dashboard/formatters';

// --- Portfolio Create/Edit Modal ---

interface PortfolioModalProps {
  opened: boolean;
  onClose: () => void;
  mode: 'create' | 'edit';
  formError: string | null;
  formName: string;
  onFormNameChange: (value: string) => void;
  formBaseCurrency: string;
  onFormBaseCurrencyChange: (value: string) => void;
  formTimezone: string;
  onFormTimezoneChange: (value: string) => void;
  formTargetNotional: number | string;
  onFormTargetNotionalChange: (value: number | string) => void;
  formCashBalance: number | string;
  onFormCashBalanceChange: (value: number | string) => void;
  saving: boolean;
  onSave: () => void;
}

export function PortfolioModal({
  opened,
  onClose,
  mode,
  formError,
  formName,
  onFormNameChange,
  formBaseCurrency,
  onFormBaseCurrencyChange,
  formTimezone,
  onFormTimezoneChange,
  formTargetNotional,
  onFormTargetNotionalChange,
  formCashBalance,
  onFormCashBalanceChange,
  saving,
  onSave,
}: PortfolioModalProps) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={mode === 'create' ? 'Nuovo Portfolio' : 'Modifica Portfolio'}
      centered
    >
      <Stack>
        {formError && <Alert color="red">{formError}</Alert>}
        <TextInput
          label="Nome"
          value={formName}
          onChange={(event) => onFormNameChange(event.currentTarget.value)}
          placeholder="Es. Portafoglio ETF"
        />
        <TextInput
          label="Valuta Base"
          value={formBaseCurrency}
          onChange={(event) => onFormBaseCurrencyChange(event.currentTarget.value.toUpperCase())}
          placeholder="EUR"
          maxLength={3}
        />
        <TextInput
          label="Timezone"
          value={formTimezone}
          onChange={(event) => onFormTimezoneChange(event.currentTarget.value)}
          placeholder="Europe/Rome"
        />
        <NumberInput
          label={`Controvalore target (${formBaseCurrency || 'EUR'})`}
          value={formTargetNotional}
          onChange={onFormTargetNotionalChange}
          min={0}
          decimalScale={2}
          placeholder="Es. 100000"
          description="Opzionale. Usato per calcolare il controvalore target per asset dai pesi %."
        />
        <NumberInput
          label={`Cash disponibile (${formBaseCurrency || 'EUR'})`}
          value={formCashBalance}
          onChange={onFormCashBalanceChange}
          min={0}
          decimalScale={2}
          placeholder="Es. 5000"
          description="Liquidità non investita nel portfolio."
        />
        <Button onClick={onSave} loading={saving}>
          {mode === 'create' ? 'Crea Portfolio' : 'Salva Modifiche'}
        </Button>
      </Stack>
    </Modal>
  );
}

// --- Portfolio Clone Modal ---

interface PortfolioCloneModalProps {
  opened: boolean;
  onClose: () => void;
  cloneName: string;
  onCloneNameChange: (value: string) => void;
  cloneError: string | null;
  cloning: boolean;
  onClone: () => void;
}

export function PortfolioCloneModal({
  opened,
  onClose,
  cloneName,
  onCloneNameChange,
  cloneError,
  cloning,
  onClone,
}: PortfolioCloneModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Clona portfolio" centered>
      <Stack>
        {cloneError && <Alert color="red">{cloneError}</Alert>}
        <Text size="sm">
          Verranno copiate solo le impostazioni del portfolio e l&apos;allocazione target. Le transazioni non saranno copiate.
        </Text>
        <TextInput
          label="Nome nuovo portfolio"
          value={cloneName}
          onChange={(event) => onCloneNameChange(event.currentTarget.value)}
          placeholder="Es. Portafoglio ETF (Copia)"
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={cloning}>
            Annulla
          </Button>
          <Button leftSection={<IconCopy size={16} />} onClick={onClone} loading={cloning}>
            Clona
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// --- Portfolio Delete Modal ---

interface PortfolioDeleteModalProps {
  opened: boolean;
  onClose: () => void;
  selectedPortfolio: Portfolio | null;
  deleting: boolean;
  onDelete: () => void;
}

export function PortfolioDeleteModal({
  opened,
  onClose,
  selectedPortfolio,
  deleting,
  onDelete,
}: PortfolioDeleteModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Conferma eliminazione portfolio" centered>
      <Stack>
        <Text size="sm">
          Vuoi eliminare il portfolio {selectedPortfolio ? `"${selectedPortfolio.name}"` : ''}?
        </Text>
        <Text size="sm" c="dimmed">
          Verranno rimossi anche i pesi target e le eventuali transazioni collegate.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={deleting}>
            Annulla
          </Button>
          <Button color="red" onClick={onDelete} loading={deleting}>
            Elimina Portfolio
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// --- Edit Transaction Modal ---

interface EditTransactionModalProps {
  opened: boolean;
  onClose: () => void;
  label: string | null;
  error: string | null;
  tradeAt: string;
  onTradeAtChange: (value: string) => void;
  quantity: number | string;
  onQuantityChange: (value: number | string) => void;
  price: number | string;
  onPriceChange: (value: number | string) => void;
  fees: number | string;
  onFeesChange: (value: number | string) => void;
  taxes: number | string;
  onTaxesChange: (value: number | string) => void;
  notes: string;
  onNotesChange: (value: string) => void;
  saving: boolean;
  onSave: () => void;
}

export function EditTransactionModal({
  opened,
  onClose,
  label,
  error,
  tradeAt,
  onTradeAtChange,
  quantity,
  onQuantityChange,
  price,
  onPriceChange,
  fees,
  onFeesChange,
  taxes,
  onTaxesChange,
  notes,
  onNotesChange,
  saving,
  onSave,
}: EditTransactionModalProps) {
  const grossTotal = formatGrossTotal(quantity, price);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`Modifica Transazione${label ? ` - ${label}` : ''}`}
      centered
    >
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        <TextInput
          label="Data / ora operazione"
          type="datetime-local"
          value={tradeAt}
          onChange={(event) => onTradeAtChange(event.currentTarget.value)}
        />
        <NumberInput label="Quantita" value={quantity} onChange={onQuantityChange} min={0} decimalScale={8} />
        <NumberInput label="Prezzo" value={price} onChange={onPriceChange} min={0} decimalScale={6} />
        <TextInput
          label="Totale (Prezzo x Quantita)"
          value={grossTotal}
          readOnly
          placeholder="Calcolato automaticamente"
        />
        <NumberInput label="Fee" value={fees} onChange={onFeesChange} min={0} decimalScale={4} />
        <NumberInput label="Tasse" value={taxes} onChange={onTaxesChange} min={0} decimalScale={4} />
        <TextInput label="Note" value={notes} onChange={(event) => onNotesChange(event.currentTarget.value)} />
        <Button onClick={onSave} loading={saving}>
          Salva Modifiche
        </Button>
      </Stack>
    </Modal>
  );
}

// --- Delete Transaction Confirmation Modal ---

interface DeleteTransactionModalProps {
  opened: boolean;
  onClose: () => void;
  label: string | null;
  deleting: boolean;
  deletingId: number | null;
  transactionId: number | null;
  onConfirm: () => void;
}

export function DeleteTransactionModal({
  opened,
  onClose,
  label,
  deleting,
  deletingId,
  transactionId,
  onConfirm,
}: DeleteTransactionModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Conferma eliminazione transazione" centered>
      <Stack>
        <Text size="sm">
          Vuoi eliminare la transazione {label ? `"${label}"` : ''}?
        </Text>
        <Text size="sm" c="dimmed">
          L'operazione aggiornera' automaticamente storico, posizioni e dashboard.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={deleting}>
            Annulla
          </Button>
          <Button
            color="red"
            onClick={onConfirm}
            loading={deletingId === transactionId}
          >
            Elimina Transazione
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
