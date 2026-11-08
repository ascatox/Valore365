import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Drawer,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useIsMobile } from '../../../hooks/useIsMobile';
import { IconPlus } from '@tabler/icons-react';
import {
  createCashMovement,
  getPortfolioCashBalance,
  type CashBalanceResponse,
  type CashBreakdown,
  type CashMovementCreateInput,
} from '../../../services/api';

interface CashSectionProps {
  selectedPortfolioId: string | null;
  baseCurrency: string;
  onMovementCreated?: () => void;
}

const SIDE_LABELS: Record<string, string> = {
  deposit: 'Deposito',
  withdrawal: 'Prelievo',
  dividend: 'Dividendo',
  fee: 'Commissione',
  interest: 'Interesse',
};

const SIDE_COLORS: Record<string, string> = {
  deposit: 'green',
  withdrawal: 'red',
  dividend: 'blue',
  fee: 'orange',
  interest: 'teal',
};

// TASK-49: composition of the cash (same model as the performance), in the
// order of the fold. sign: +1 adds to the cash, -1 takes from it.
const BREAKDOWN_LINES: { key: keyof CashBreakdown; label: string; sign: 1 | -1 }[] = [
  { key: 'opening_balance', label: 'Saldo iniziale', sign: 1 },
  { key: 'deposits', label: 'Depositi', sign: 1 },
  { key: 'withdrawals', label: 'Prelievi', sign: -1 },
  { key: 'dividends', label: 'Dividendi netti', sign: 1 },
  { key: 'interest', label: 'Interessi', sign: 1 },
  { key: 'fees', label: 'Commissioni', sign: -1 },
  { key: 'buys', label: 'Acquisti', sign: -1 },
  { key: 'sells', label: 'Vendite', sign: 1 },
  { key: 'implicit_contributions', label: 'Apporti impliciti', sign: 1 },
];

const formatAmount = (value: number) =>
  value.toLocaleString('it-IT', { useGrouping: 'always', minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function CashSection({ selectedPortfolioId, baseCurrency, onMovementCreated }: CashSectionProps) {
  const isMobile = useIsMobile();
  const [cashData, setCashData] = useState<CashBalanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [drawerOpened, setDrawerOpened] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [side, setSide] = useState<string>('deposit');
  const [quantity, setQuantity] = useState<number | string>('');
  const [currency, setCurrency] = useState(baseCurrency || 'EUR');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    setCurrency(baseCurrency || 'EUR');
  }, [baseCurrency]);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setCashData(null);
      return;
    }
    const load = async () => {
      try {
        setLoading(true);
        const data = await getPortfolioCashBalance(Number(selectedPortfolioId));
        setCashData(data);
      } catch {
        setCashData(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [selectedPortfolioId]);

  const handleSubmit = async () => {
    if (!selectedPortfolioId || !quantity) return;
    try {
      setSubmitting(true);
      setError(null);
      const payload: CashMovementCreateInput = {
        portfolio_id: Number(selectedPortfolioId),
        side: side as CashMovementCreateInput['side'],
        trade_at: new Date().toISOString(),
        quantity: Number(quantity),
        trade_currency: currency,
        notes: notes || undefined,
      };
      await createCashMovement(payload);
      setDrawerOpened(false);
      setQuantity('');
      setNotes('');
      // Reload
      const data = await getPortfolioCashBalance(Number(selectedPortfolioId));
      setCashData(data);
      onMovementCreated?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (!selectedPortfolioId) return null;

  return (
    <>
      <Card withBorder mt="lg">
        <Group justify="space-between" mb="sm">
          <Title order={4}>Liquidità</Title>
          <Group gap="xs">
            {loading && <Loader size="xs" />}
            <Button
              size="xs"
              leftSection={<IconPlus size={14} />}
              visibleFrom="sm"
              onClick={() => setDrawerOpened(true)}
            >
              Registra Movimento
            </Button>
          </Group>
        </Group>

        {cashData && (
          <>
            <Group mb="md" gap="lg">
              <div>
                <Text size="sm" c="dimmed">Saldo Totale</Text>
                <Text size="xl" fw={700} c={cashData.total_cash >= 0 ? 'teal' : 'red'}>
                  {cashData.total_cash.toLocaleString('it-IT', { useGrouping: 'always', minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </Text>
              </div>
              {cashData.currency_breakdown.map((b) => (
                <div key={b.currency}>
                  <Text size="sm" c="dimmed">{b.currency}</Text>
                  <Text size="lg" fw={600}>
                    {b.balance.toLocaleString('it-IT', { useGrouping: 'always', minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </Text>
                </div>
              ))}
            </Group>

            {cashData.cash_breakdown && (
              <Stack gap={2} mb="md" data-testid="cash-breakdown">
                {BREAKDOWN_LINES.filter(({ key }) => Math.abs(cashData.cash_breakdown?.[key] ?? 0) >= 0.005).map(
                  ({ key, label, sign }) => (
                    <Group key={key} justify="space-between" gap="xs">
                      <Text size="sm" c="dimmed">{label}</Text>
                      <Text size="sm" fw={500}>
                        {sign < 0 ? '−' : '+'}
                        {formatAmount(cashData.cash_breakdown?.[key] ?? 0)}
                      </Text>
                    </Group>
                  ),
                )}
                <Group justify="space-between" gap="xs">
                  <Text size="sm" fw={600}>= Liquidità</Text>
                  <Text size="sm" fw={700}>{formatAmount(cashData.total_cash)}</Text>
                </Group>
                {cashData.cash_model_note && (
                  <Text size="xs" c="dimmed" mt={4}>{cashData.cash_model_note}</Text>
                )}
              </Stack>
            )}

            {cashData.recent_movements.length > 0 && (
              <Table.ScrollContainer minWidth={400}>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Data</Table.Th>
                      <Table.Th>Tipo</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Importo</Table.Th>
                      <Table.Th>Note</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {cashData.recent_movements.map((m) => (
                      <Table.Tr key={m.id}>
                        <Table.Td>{new Date(m.trade_at).toLocaleDateString('it-IT')}</Table.Td>
                        <Table.Td>
                          <Badge color={SIDE_COLORS[m.side] || 'gray'} size="sm">
                            {SIDE_LABELS[m.side] || m.side}
                          </Badge>
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          {(m.quantity * m.price).toLocaleString('it-IT', { useGrouping: 'always', minimumFractionDigits: 2 })} {m.trade_currency}
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" c="dimmed" lineClamp={1}>{m.notes || '-'}</Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}

            {cashData.recent_movements.length === 0 && (
              <Text c="dimmed" ta="center">Nessun movimento di cassa registrato</Text>
            )}
          </>
        )}
      </Card>

      <Drawer
        opened={drawerOpened}
        onClose={() => setDrawerOpened(false)}
        title="Registra Movimento di Cassa"
        position={isMobile ? 'bottom' : 'right'}
        size={isMobile ? '100%' : 'md'}
        radius={isMobile ? '24px 24px 0 0' : undefined}
        styles={{
          content: { paddingBottom: 'var(--safe-area-bottom)' },
          body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
        }}
      >
        <Stack>
          <Select
            label="Tipo Movimento"
            data={[
              { value: 'deposit', label: 'Deposito' },
              { value: 'withdrawal', label: 'Prelievo' },
              { value: 'dividend', label: 'Dividendo' },
              { value: 'fee', label: 'Commissione' },
              { value: 'interest', label: 'Interesse' },
            ]}
            value={side}
            onChange={(v) => setSide(v ?? 'deposit')}
          />
          <NumberInput
            label="Importo"
            placeholder="0,00"
            min={0.01}
            decimalScale={2}
            value={quantity}
            onChange={setQuantity}
          />
          <TextInput
            label="Valuta"
            value={currency}
            onChange={(e) => setCurrency(e.currentTarget.value.toUpperCase())}
            maxLength={3}
          />
          <TextInput
            label="Note"
            placeholder="Opzionale"
            value={notes}
            onChange={(e) => setNotes(e.currentTarget.value)}
          />
          {error && <Text c="red" size="sm">{error}</Text>}
          <Button onClick={handleSubmit} loading={submitting} disabled={!quantity}>
            Conferma
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
