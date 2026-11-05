import {
  ActionIcon,
  Card,
  Checkbox,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Button,
} from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import type { DoctorScenarioInput, DoctorScenarioMode, DoctorScenarioOperation, Position } from '../../../services/api/types';

interface ScenarioBuilderProps {
  value: DoctorScenarioInput;
  onChange: (value: DoctorScenarioInput) => void;
  positions: Position[];
  isAggregate: boolean;
  index: number;
  onRemove?: () => void;
  hint?: string | null;
}

const toNumber = (value: number | string, fallback = 0): number => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback;
  const parsed = Number(value.replace(',', '.'));
  return value.trim() !== '' && Number.isFinite(parsed) ? parsed : fallback;
};

const MODE_LABELS: Record<DoctorScenarioMode, string> = {
  manual: 'Acquisti/vendite',
  new_cash_only: 'Solo nuova liquidità',
  rebalance: 'Ribilanciamento',
};

/** Inputs of one what-if scenario; the simulation itself runs on the backend. */
export function ScenarioBuilder({ value, onChange, positions, isAggregate, index, onRemove, hint }: ScenarioBuilderProps) {
  const set = (patch: Partial<DoctorScenarioInput>) => onChange({ ...value, ...patch });
  const setConstraints = (patch: Partial<DoctorScenarioInput['constraints']>) => set({ constraints: { ...value.constraints, ...patch } });
  // Aggregate scope: overall weights only, no per-account buy/sell orders.
  const modes: DoctorScenarioMode[] = isAggregate ? ['new_cash_only', 'rebalance'] : ['manual', 'new_cash_only', 'rebalance'];
  const symbolOptions = positions.map((position) => ({ value: position.symbol, label: `${position.symbol} · ${position.name}` }));
  const updateOperation = (position: number, patch: Partial<DoctorScenarioOperation>) => set({
    operations: value.operations.map((operation, current) => (current === position ? { ...operation, ...patch } : operation)),
  });

  return (
    <Card withBorder radius="lg" padding="md" data-testid={`scenario-builder-${index}`}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <TextInput
            label={`Scenario ${String.fromCharCode(65 + index)}`}
            value={value.label}
            onChange={(event) => set({ label: event.currentTarget.value })}
            maxLength={60}
            style={{ flex: 1 }}
          />
          {onRemove && (
            <ActionIcon variant="subtle" color="red" onClick={onRemove} aria-label={`Rimuovi scenario ${String.fromCharCode(65 + index)}`} mt={22}>
              <IconTrash size={16} />
            </ActionIcon>
          )}
        </Group>
        {hint && <Text size="xs" c="dimmed">{hint}</Text>}
        <Stack gap={4}>
          <Text size="sm" fw={500} id={`scenario-mode-${index}`}>Tipo di simulazione</Text>
          <SegmentedControl
            aria-labelledby={`scenario-mode-${index}`}
            value={modes.includes(value.mode) ? value.mode : modes[0]}
            onChange={(mode) => set({
              mode: mode as DoctorScenarioMode,
              constraints: { ...value.constraints, no_sell: mode === 'new_cash_only' ? true : value.constraints.no_sell },
            })}
            data={modes.map((mode) => ({ value: mode, label: MODE_LABELS[mode] }))}
            fullWidth
          />
        </Stack>

        <NumberInput
          label="Nuova liquidità da investire"
          value={value.new_cash}
          onChange={(amount) => set({ new_cash: Math.max(0, toNumber(amount)) })}
          min={0}
          thousandSeparator="."
          decimalSeparator=","
        />

        {value.mode === 'manual' && !isAggregate && (
          <Stack gap="xs">
            <Text size="sm" fw={500}>Operazioni ipotetiche</Text>
            {value.operations.map((operation, position) => (
              <Group key={position} gap="xs" align="flex-end" wrap="wrap">
                <Select
                  label="Strumento"
                  data={symbolOptions}
                  value={operation.symbol ?? null}
                  onChange={(symbol) => updateOperation(position, { symbol: symbol ?? undefined })}
                  searchable
                  w={200}
                />
                <SegmentedControl
                  aria-label="Operazione"
                  value={operation.action}
                  onChange={(action) => updateOperation(position, { action: action as 'buy' | 'sell' })}
                  data={[{ value: 'buy', label: 'Acquisto' }, { value: 'sell', label: 'Vendita' }]}
                />
                <NumberInput
                  label="Importo"
                  value={operation.amount}
                  onChange={(amount) => updateOperation(position, { amount: Math.max(0, toNumber(amount)) })}
                  min={0}
                  thousandSeparator="."
                  decimalSeparator=","
                  w={140}
                />
                <ActionIcon
                  variant="subtle"
                  color="red"
                  aria-label="Rimuovi operazione"
                  onClick={() => set({ operations: value.operations.filter((_, current) => current !== position) })}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Group>
            ))}
            <Button
              variant="light"
              size="xs"
              w="fit-content"
              leftSection={<IconPlus size={14} />}
              onClick={() => set({ operations: [...value.operations, { symbol: positions[0]?.symbol, action: 'buy', amount: 0 }] })}
            >
              Aggiungi operazione
            </Button>
          </Stack>
        )}

        {value.mode === 'rebalance' && (
          <Stack gap="xs">
            <Text size="sm" fw={500}>{isAggregate ? 'Pesi obiettivo complessivi (%)' : 'Pesi obiettivo (%)'}</Text>
            {positions.length === 0 && <Text size="sm" c="dimmed">Nessuna posizione da ribilanciare.</Text>}
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
              {positions.map((position) => (
                <NumberInput
                  key={position.asset_id}
                  label={position.symbol}
                  value={value.target_weights[String(position.asset_id)] ?? ''}
                  onChange={(weight) => {
                    const next = { ...value.target_weights };
                    if (weight === '' || weight == null) delete next[String(position.asset_id)];
                    else next[String(position.asset_id)] = Math.max(0, toNumber(weight));
                    set({ target_weights: next });
                  }}
                  min={0}
                  max={100}
                  decimalSeparator=","
                />
              ))}
            </SimpleGrid>
          </Stack>
        )}

        <Stack gap={6}>
          <Text size="sm" fw={500}>Vincoli</Text>
          <Checkbox
            label="Nessuna vendita"
            checked={value.constraints.no_sell}
            disabled={value.mode === 'new_cash_only'}
            onChange={(event) => setConstraints({ no_sell: event.currentTarget.checked })}
          />
          <Checkbox
            label="Mantieni invariata la quota azionaria complessiva"
            checked={value.constraints.keep_equity_total}
            onChange={(event) => setConstraints({ keep_equity_total: event.currentTarget.checked })}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
            <NumberInput
              label="Turnover massimo (%)"
              value={value.constraints.max_turnover_pct ?? ''}
              onChange={(turnover) => setConstraints({ max_turnover_pct: turnover === '' ? null : Math.max(0, toNumber(turnover)) })}
              min={0}
              max={100}
              decimalSeparator=","
            />
            <NumberInput
              label="Commissioni ipotetiche (%)"
              value={value.fee_model.pct}
              onChange={(fee) => set({ fee_model: { ...value.fee_model, pct: Math.max(0, toNumber(fee)) } })}
              min={0}
              max={10}
              decimalSeparator=","
            />
            <NumberInput
              label="Commissione fissa per operazione"
              value={value.fee_model.fixed}
              onChange={(fee) => set({ fee_model: { ...value.fee_model, fixed: Math.min(10000, Math.max(0, toNumber(fee))) } })}
              min={0}
              max={10000}
              thousandSeparator="."
              decimalSeparator=","
            />
          </SimpleGrid>
          <Checkbox
            label="Usa anche la liquidità già presente nel portafoglio"
            description="Se disattivato, la simulazione usa solo la nuova liquidità e le eventuali vendite."
            checked={value.constraints.use_cash_balance ?? false}
            onChange={(event) => setConstraints({ use_cash_balance: event.currentTarget.checked })}
          />
        </Stack>
      </Stack>
    </Card>
  );
}
