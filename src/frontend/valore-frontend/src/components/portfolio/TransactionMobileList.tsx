import { Fragment, useState } from 'react';
import { Box, Button, Drawer, Group, SimpleGrid, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconArrowDownLeft, IconArrowUpRight, IconEdit, IconTrash } from '@tabler/icons-react';
import type { TransactionListItem } from '../../services/api';
import {
  formatDateTime,
  formatMoneyOrNA,
  formatNum,
  formatTransactionSideLabel,
  getTransactionSideColor,
} from '../dashboard/formatters';
import { BOTTOM_SHEET_PROPS } from '../mobile/bottomSheet';

interface TransactionMobileListProps {
  transactions: TransactionListItem[];
  /** Group rows under a date heading (only meaningful when sorted by date). */
  groupByDate: boolean;
  totalLabel?: string | null;
  deletingId?: number | null;
  onEdit: (tx: TransactionListItem) => void;
  onDelete: (tx: TransactionListItem) => void;
}

// Money flowing into the portfolio's positions or cash vs out of it.
const INBOUND_SIDES = new Set(['buy', 'deposit', 'dividend', 'interest']);

function transactionTotal(tx: TransactionListItem): number {
  const gross = tx.quantity * tx.price;
  const costs = (tx.fees ?? 0) + (tx.taxes ?? 0);
  return tx.side === 'buy' ? gross + costs : gross - costs;
}

function dayKey(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toDateString();
}

function dayLabel(value: string): string {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' });
}

// Statement-style list: one row per movement, details and the edit/delete
// actions in a bottom sheet so destructive buttons aren't repeated in the list.
export function TransactionMobileList({
  transactions,
  groupByDate,
  totalLabel,
  deletingId,
  onEdit,
  onDelete,
}: TransactionMobileListProps) {
  const [selected, setSelected] = useState<TransactionListItem | null>(null);

  return (
    <Stack gap="xs">
      <Box
        style={{
          borderRadius: 'var(--mantine-radius-md)',
          border: '1px solid var(--mantine-color-default-border)',
          background: 'var(--mantine-color-body)',
          overflow: 'hidden',
        }}
      >
        {transactions.map((tx, index) => {
          const showHeading = groupByDate && (index === 0 || dayKey(transactions[index - 1].trade_at) !== dayKey(tx.trade_at));
          const color = getTransactionSideColor(tx.side);
          const Icon = INBOUND_SIDES.has(tx.side) ? IconArrowDownLeft : IconArrowUpRight;
          return (
            <Fragment key={tx.id}>
              {showHeading && (
                <Text
                  size="xs"
                  fw={700}
                  tt="uppercase"
                  c="dimmed"
                  px="md"
                  pt={index === 0 ? 'sm' : 'md'}
                  pb={4}
                  style={{ letterSpacing: 0.6, borderTop: index === 0 ? undefined : '1px solid var(--mantine-color-default-border)' }}
                >
                  {dayLabel(tx.trade_at)}
                </Text>
              )}
              <UnstyledButton
                onClick={() => setSelected(tx)}
                aria-label={`${formatTransactionSideLabel(tx.side)} ${tx.symbol ?? ''}: dettagli`}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '10px 16px',
                  borderTop: showHeading || index === 0 ? undefined : '1px solid var(--mantine-color-default-border)',
                }}
              >
                <Group gap={12} wrap="nowrap">
                  <Box
                    style={{
                      width: 32,
                      height: 32,
                      flexShrink: 0,
                      borderRadius: '50%',
                      display: 'grid',
                      placeItems: 'center',
                      background: `var(--mantine-color-${color}-light)`,
                      color: `var(--mantine-color-${color}-light-color)`,
                    }}
                  >
                    <Icon size={16} />
                  </Box>
                  <Box style={{ minWidth: 0, flex: 1 }}>
                    <Text fw={700} size="sm" truncate="end">
                      {`${formatTransactionSideLabel(tx.side)} ${tx.symbol ?? ''}`.trim()}
                    </Text>
                    <Text size="xs" c="dimmed" truncate="end">
                      {`${formatNum(tx.quantity, 4)} × ${formatMoneyOrNA(tx.price, tx.trade_currency)}`}
                    </Text>
                  </Box>
                  <Text fw={700} size="sm" style={{ flexShrink: 0 }}>
                    {formatMoneyOrNA(transactionTotal(tx), tx.trade_currency)}
                  </Text>
                </Group>
              </UnstyledButton>
            </Fragment>
          );
        })}
      </Box>

      {totalLabel && (
        <Group justify="space-between" px={4}>
          <Text size="sm" c="dimmed">Totale filtro</Text>
          <Text size="sm" fw={700}>{totalLabel}</Text>
        </Group>
      )}

      <Drawer
        opened={!!selected}
        onClose={() => setSelected(null)}
        {...BOTTOM_SHEET_PROPS}
        title={selected ? `${formatTransactionSideLabel(selected.side)} ${selected.symbol ?? ''}`.trim() : ''}
      >
        {selected && (
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              {[selected.asset_name, formatDateTime(selected.trade_at)].filter(Boolean).join(' · ')}
            </Text>
            <SimpleGrid cols={2} spacing="md" verticalSpacing="sm">
              <Detail label="Quantità" value={formatNum(selected.quantity, 4)} />
              <Detail label="Prezzo" value={formatMoneyOrNA(selected.price, selected.trade_currency)} />
              <Detail label="Commissioni" value={formatMoneyOrNA(selected.fees ?? 0, selected.trade_currency)} />
              <Detail label="Tasse" value={formatMoneyOrNA(selected.taxes ?? 0, selected.trade_currency)} />
              <Detail label="Lordo" value={formatMoneyOrNA(selected.quantity * selected.price, selected.trade_currency)} />
              <Detail label="Totale" value={formatMoneyOrNA(transactionTotal(selected), selected.trade_currency)} />
            </SimpleGrid>
            {!!selected.notes && (
              <Box>
                <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.6 }}>Note</Text>
                <Text size="sm">{selected.notes}</Text>
              </Box>
            )}
            <Button
              leftSection={<IconEdit size={16} />}
              onClick={() => {
                const tx = selected;
                setSelected(null);
                onEdit(tx);
              }}
            >
              Modifica
            </Button>
            {/* Opens the existing confirmation dialog; nothing is deleted from here directly. */}
            <Button
              variant="subtle"
              color="red"
              leftSection={<IconTrash size={16} />}
              loading={deletingId === selected.id}
              onClick={() => {
                const tx = selected;
                setSelected(null);
                onDelete(tx);
              }}
            >
              Elimina transazione
            </Button>
          </Stack>
        )}
      </Drawer>
    </Stack>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.6 }}>{label}</Text>
      <Text fw={700} size="sm">{value}</Text>
    </Box>
  );
}
