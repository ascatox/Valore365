import { useEffect, useState } from 'react';
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Menu,
  NumberInput,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconDotsVertical, IconPlus, IconCheck, IconPlayerSkipForward, IconTrash } from '@tabler/icons-react';
import {
  confirmPacExecution,
  deletePacRule,
  getPendingPacExecutions,
  getPortfolioPacRules,
  skipPacExecution,
  type PacExecutionConfirmInput,
  type PacExecutionRead,
  type PacRuleRead,
} from '../../services/api';

interface PacSectionProps {
  selectedPortfolioId: string | null;
  baseCurrency: string;
  onOpenPacDrawer: () => void;
  onEditPacRule?: (rule: PacRuleRead) => void;
  refreshTrigger?: number;
}

const FREQUENCY_LABELS: Record<string, string> = {
  weekly: 'Settimanale',
  biweekly: 'Bisettimanale',
  monthly: 'Mensile',
};

const DAY_LABELS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];

export function PacSection({
  selectedPortfolioId,
  baseCurrency,
  onOpenPacDrawer,
  onEditPacRule,
  refreshTrigger,
}: PacSectionProps) {
  const [rules, setRules] = useState<PacRuleRead[]>([]);
  const [pendingExecs, setPendingExecs] = useState<PacExecutionRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [confirmPrice, setConfirmPrice] = useState<number | string>('');
  const [confirmCurrency, setConfirmCurrency] = useState(baseCurrency || 'EUR');

  useEffect(() => {
    setConfirmCurrency(baseCurrency || 'EUR');
  }, [baseCurrency]);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setRules([]);
      setPendingExecs([]);
      return;
    }
    const load = async () => {
      try {
        setLoading(true);
        const [r, e] = await Promise.all([
          getPortfolioPacRules(Number(selectedPortfolioId)),
          getPendingPacExecutions(Number(selectedPortfolioId)),
        ]);
        setRules(r);
        setPendingExecs(e);
      } catch {
        setRules([]);
        setPendingExecs([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [selectedPortfolioId, refreshTrigger]);

  const handleConfirm = async (execId: number) => {
    if (!confirmPrice || Number(confirmPrice) <= 0) return;
    try {
      const payload: PacExecutionConfirmInput = {
        price: Number(confirmPrice),
        trade_currency: confirmCurrency,
      };
      await confirmPacExecution(execId, payload);
      setConfirmingId(null);
      setConfirmPrice('');
      // Reload
      if (selectedPortfolioId) {
        const e = await getPendingPacExecutions(Number(selectedPortfolioId));
        setPendingExecs(e);
      }
    } catch {
      /* ignore */
    }
  };

  const handleSkip = async (execId: number) => {
    try {
      await skipPacExecution(execId);
      if (selectedPortfolioId) {
        const e = await getPendingPacExecutions(Number(selectedPortfolioId));
        setPendingExecs(e);
      }
    } catch {
      /* ignore */
    }
  };

  const handleDelete = async (ruleId: number) => {
    try {
      await deletePacRule(ruleId);
      if (selectedPortfolioId) {
        const r = await getPortfolioPacRules(Number(selectedPortfolioId));
        setRules(r);
      }
    } catch {
      /* ignore */
    }
  };

  if (!selectedPortfolioId) return null;

  return (
    <Card withBorder mt="lg">
      <Group justify="space-between" mb="sm">
        <Title order={4}>Piani di Accumulo (PAC)</Title>
        <Group gap="xs">
          {loading && <Loader size="xs" />}
          <Button size="xs" leftSection={<IconPlus size={14} />} onClick={onOpenPacDrawer}>
            Nuovo PAC
          </Button>
        </Group>
      </Group>

      {/* Active Rules */}
      {rules.length > 0 && (
        <Table.ScrollContainer minWidth={500}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Asset</Table.Th>
                <Table.Th>Modalità</Table.Th>
                <Table.Th>Importo/Qta</Table.Th>
                <Table.Th>Frequenza</Table.Th>
                <Table.Th>Stato</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Azioni</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rules.map((rule) => (
                <Table.Tr key={rule.id}>
                  <Table.Td>
                    <Text fw={500}>{rule.symbol}</Text>
                    <Text size="xs" c="dimmed">{rule.asset_name}</Text>
                  </Table.Td>
                  <Table.Td>{rule.mode === 'amount' ? 'Importo' : 'Quantità'}</Table.Td>
                  <Table.Td>
                    {rule.mode === 'amount'
                      ? `${rule.amount?.toLocaleString('it-IT', { minimumFractionDigits: 2 })} ${baseCurrency}`
                      : rule.quantity?.toFixed(4)
                    }
                  </Table.Td>
                  <Table.Td>
                    {FREQUENCY_LABELS[rule.frequency] || rule.frequency}
                    {rule.frequency === 'monthly' && rule.day_of_month && ` (g. ${rule.day_of_month})`}
                    {(rule.frequency === 'weekly' || rule.frequency === 'biweekly') && rule.day_of_week != null && ` (${DAY_LABELS[rule.day_of_week]})`}
                  </Table.Td>
                  <Table.Td>
                    <Badge color={rule.active ? 'green' : 'gray'} size="sm">
                      {rule.active ? 'Attivo' : 'Sospeso'}
                    </Badge>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon variant="subtle" size="sm">
                          <IconDotsVertical size={14} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        {onEditPacRule && (
                          <Menu.Item onClick={() => onEditPacRule(rule)}>Modifica</Menu.Item>
                        )}
                        <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => handleDelete(rule.id)}>
                          Elimina
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {rules.length === 0 && !loading && (
        <Text c="dimmed" ta="center" mb="md">Nessun piano di accumulo configurato</Text>
      )}

      {/* Pending Executions */}
      {pendingExecs.length > 0 && (
        <>
          <Title order={5} mt="lg" mb="sm">Esecuzioni in Attesa</Title>
          <Stack gap="xs">
            {pendingExecs.map((exec) => {
              const rule = rules.find((r) => r.id === exec.pac_rule_id);
              return (
                <Card key={exec.id} withBorder p="sm">
                  <Group justify="space-between">
                    <div>
                      <Text fw={500}>{rule?.symbol || `PAC #${exec.pac_rule_id}`}</Text>
                      <Text size="sm" c="dimmed">
                        Scadenza: {new Date(exec.scheduled_date).toLocaleDateString('it-IT')}
                        {rule && ` — ${rule.mode === 'amount' ? `${rule.amount?.toFixed(2)} ${baseCurrency}` : `${rule.quantity?.toFixed(4)} quote`}`}
                      </Text>
                    </div>
                    <Group gap="xs">
                      {confirmingId === exec.id ? (
                        <>
                          <NumberInput
                            placeholder="Prezzo"
                            size="xs"
                            w={100}
                            min={0.01}
                            decimalScale={4}
                            value={confirmPrice}
                            onChange={setConfirmPrice}
                          />
                          <TextInput
                            size="xs"
                            w={60}
                            value={confirmCurrency}
                            onChange={(e) => setConfirmCurrency(e.currentTarget.value.toUpperCase())}
                          />
                          <Button size="xs" color="green" onClick={() => handleConfirm(exec.id)}>OK</Button>
                          <Button size="xs" variant="outline" onClick={() => setConfirmingId(null)}>X</Button>
                        </>
                      ) : (
                        <>
                          <Button
                            size="xs"
                            color="green"
                            leftSection={<IconCheck size={14} />}
                            onClick={() => setConfirmingId(exec.id)}
                          >
                            Conferma
                          </Button>
                          <Button
                            size="xs"
                            variant="outline"
                            color="gray"
                            leftSection={<IconPlayerSkipForward size={14} />}
                            onClick={() => handleSkip(exec.id)}
                          >
                            Salta
                          </Button>
                        </>
                      )}
                    </Group>
                  </Group>
                </Card>
              );
            })}
          </Stack>
        </>
      )}
    </Card>
  );
}
