import {
  Alert,
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import type { RebalancePreviewResponse, RebalanceCommitResponse } from '../../../services/api';
import { formatNum, formatMoneyOrNA as formatMoney } from '../../dashboard/formatters';

interface RebalancePreviewModalProps {
  opened: boolean;
  onClose: () => void;
  baseCurrency: string;
  // Rebalance config
  rebalanceMode: 'buy_only' | 'rebalance' | 'sell_only';
  onRebalanceModeChange: (value: 'buy_only' | 'rebalance' | 'sell_only') => void;
  rebalanceMaxTransactions: number | string;
  onRebalanceMaxTransactionsChange: (value: number | string) => void;
  rebalanceMinOrderValue: number | string;
  onRebalanceMinOrderValueChange: (value: number | string) => void;
  rebalanceCashToAllocate: number | string;
  onRebalanceCashToAllocateChange: (value: number | string) => void;
  rebalanceTradeAt: string;
  onRebalanceTradeAtChange: (value: string) => void;
  rebalanceRounding: 'fractional' | 'integer';
  onRebalanceRoundingChange: (value: 'fractional' | 'integer') => void;
  // Preview data
  rebalancePreviewError: string | null;
  rebalancePreviewData: RebalancePreviewResponse | null;
  rebalancePreviewLoading: boolean;
  rebalanceCommitResult: RebalanceCommitResponse | null;
  rebalanceCommitLoading: boolean;
  rebalanceSelectedRows: Record<string, boolean>;
  onRebalanceSelectedRowsChange: (value: Record<string, boolean>) => void;
  // Actions
  onLoadPreview: () => void;
  onCommitPreview: () => void;
}

export function RebalancePreviewModal({
  opened,
  onClose,
  baseCurrency,
  rebalanceMode,
  onRebalanceModeChange,
  rebalanceMaxTransactions,
  onRebalanceMaxTransactionsChange,
  rebalanceMinOrderValue,
  onRebalanceMinOrderValueChange,
  rebalanceCashToAllocate,
  onRebalanceCashToAllocateChange,
  rebalanceTradeAt,
  onRebalanceTradeAtChange,
  rebalanceRounding,
  onRebalanceRoundingChange,
  rebalancePreviewError,
  rebalancePreviewData,
  rebalancePreviewLoading,
  rebalanceCommitResult,
  rebalanceCommitLoading,
  rebalanceSelectedRows,
  onRebalanceSelectedRowsChange,
  onLoadPreview,
  onCommitPreview,
}: RebalancePreviewModalProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Genera transazioni da target (Preview)"
      size={isMobile ? '100%' : 'min(1100px, 95vw)'}
      fullScreen={isMobile}
      centered={!isMobile}
      styles={{
        body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
      }}
    >
      <Stack>
        {rebalancePreviewError && <Alert color="red">{rebalancePreviewError}</Alert>}

        <Select
          label="Modalita"
          value={rebalanceMode}
          onChange={(value) => onRebalanceModeChange((value as 'buy_only' | 'rebalance' | 'sell_only') ?? 'buy_only')}
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
            onChange={onRebalanceMaxTransactionsChange}
            min={1}
            max={100}
          />
          <NumberInput
            label="Soglia minima ordine"
            value={rebalanceMinOrderValue}
            onChange={onRebalanceMinOrderValueChange}
            min={0}
            decimalScale={2}
          />
        </Group>

        {rebalanceMode === 'buy_only' && (
          <NumberInput
            label={`Importo da allocare (${baseCurrency})`}
            value={rebalanceCashToAllocate}
            onChange={onRebalanceCashToAllocateChange}
            min={0}
            decimalScale={2}
          />
        )}

        <TextInput
          label="Data / ora operazioni (preview)"
          type="datetime-local"
          value={rebalanceTradeAt}
          onChange={(event) => onRebalanceTradeAtChange(event.currentTarget.value)}
        />

        <SegmentedControl
          value={rebalanceRounding}
          onChange={(value) => onRebalanceRoundingChange((value as 'fractional' | 'integer') ?? 'fractional')}
          data={[
            { value: 'fractional', label: 'Quantita decimali' },
            { value: 'integer', label: 'Quantita intere' },
          ]}
        />

        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            Preview senza salvataggio. Le transazioni non vengono ancora create.
          </Text>
          <Button onClick={onLoadPreview} loading={rebalancePreviewLoading}>
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
                          onRebalanceSelectedRowsChange(
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
                              onRebalanceSelectedRowsChange({ ...rebalanceSelectedRows, [key]: checked });
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
                        <Table.Td style={{ textAlign: 'right' }}>{formatNum(item.target_weight_pct)}%</Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>{formatNum(item.current_weight_pct)}%</Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          <Text c={item.drift_pct >= 0 ? 'orange' : 'teal'} fw={600} span>
                            {item.drift_pct > 0 ? '+' : ''}{formatNum(item.drift_pct)}%
                          </Text>
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          {formatMoney(item.price, item.trade_currency)}
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>{formatNum(item.quantity, 4)}</Table.Td>
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
                onClick={onCommitPreview}
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
  );
}
