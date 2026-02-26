import { useState, useMemo } from 'react';
import { Group, Progress, Table, Text, UnstyledButton } from '@mantine/core';
import { IconChevronUp, IconChevronDown, IconSelector } from '@tabler/icons-react';
import type { Position, PortfolioSummary } from '../../../services/api';
import { formatMoney, formatPct, getVariationColor } from '../formatters';

type SortKey = 'symbol' | 'quantity' | 'market_value' | 'unrealized_pl' | 'unrealized_pl_pct' | 'weight' | 'first_trade_at';

interface HoldingsTableProps {
  positions: Position[];
  currency: string;
  summary?: PortfolioSummary | null;
}

interface ColumnDef {
  label: string;
  key: SortKey;
  align: 'left' | 'right';
  visibleFrom?: 'sm' | 'md';
  sortable: boolean;
}

const columns: ColumnDef[] = [
  { label: 'Asset', key: 'symbol', align: 'left', sortable: true },
  { label: 'Qta', key: 'quantity', align: 'right', visibleFrom: 'sm', sortable: true },
  { label: 'Valore', key: 'market_value', align: 'right', sortable: true },
  { label: 'P/L', key: 'unrealized_pl', align: 'right', sortable: true },
  { label: 'P/L %', key: 'unrealized_pl_pct', align: 'right', sortable: true },
  { label: 'Alloc.', key: 'weight', align: 'right', sortable: true },
  { label: 'Prima Op.', key: 'first_trade_at', align: 'right', visibleFrom: 'md', sortable: true },
];

function SortIcon({ column, sortKey, sortDir }: { column: SortKey; sortKey: SortKey; sortDir: 'asc' | 'desc' }) {
  if (column !== sortKey) return <IconSelector size={14} stroke={1.5} style={{ opacity: 0.4 }} />;
  return sortDir === 'asc' ? <IconChevronUp size={14} stroke={1.5} /> : <IconChevronDown size={14} stroke={1.5} />;
}

function getSortValue(p: Position, key: SortKey): number | string {
  switch (key) {
    case 'symbol': return p.symbol.toLowerCase();
    case 'quantity': return p.quantity;
    case 'market_value': return p.market_value;
    case 'unrealized_pl': return p.unrealized_pl;
    case 'unrealized_pl_pct': return p.unrealized_pl_pct;
    case 'weight': return p.weight;
    case 'first_trade_at': return p.first_trade_at ?? '';
    default: return 0;
  }
}

function formatFirstTrade(value?: string | null): string {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleDateString('it-IT', { month: '2-digit', year: '2-digit' });
}

export function HoldingsTable({ positions, currency, summary }: HoldingsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('market_value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sorted = useMemo(() => {
    const copy = [...positions];
    copy.sort((a, b) => {
      const av = getSortValue(a, sortKey);
      const bv = getSortValue(b, sortKey);
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [positions, sortKey, sortDir]);

  const totals = useMemo(() => {
    const totalValue = summary?.market_value ?? positions.reduce((s, p) => s + p.market_value, 0);
    const totalPl = summary?.unrealized_pl ?? positions.reduce((s, p) => s + p.unrealized_pl, 0);
    const totalCost = summary?.cost_basis ?? positions.reduce((s, p) => s + (p.market_value - p.unrealized_pl), 0);
    const totalPlPct = summary?.unrealized_pl_pct ?? (totalCost > 0 ? (totalPl / totalCost) * 100 : 0);
    return { totalValue, totalPl, totalPlPct };
  }, [positions, summary]);

  return (
    <Table.ScrollContainer minWidth={500}>
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          {columns.map((col) => (
            <Table.Th
              key={col.key}
              style={{ textAlign: col.align }}
              visibleFrom={col.visibleFrom}
            >
              {col.sortable ? (
                <UnstyledButton onClick={() => handleSort(col.key)} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Text fw={600} size="xs" component="span">{col.label}</Text>
                  <SortIcon column={col.key} sortKey={sortKey} sortDir={sortDir} />
                </UnstyledButton>
              ) : (
                <Text fw={600} size="xs" component="span">{col.label}</Text>
              )}
            </Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {sorted.length ? (
          <>
            {sorted.map((p) => (
              <Table.Tr key={p.asset_id}>
                {/* Asset */}
                <Table.Td>
                  <Text fw={500} size="sm">{p.symbol}</Text>
                  <Text size="xs" c="dimmed" lineClamp={1}>{p.name}</Text>
                </Table.Td>
                {/* Qta */}
                <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">
                  <Text size="sm">{p.quantity.toFixed(2)}</Text>
                </Table.Td>
                {/* Valore */}
                <Table.Td style={{ textAlign: 'right' }}>
                  <Text size="sm">{formatMoney(p.market_value, currency)}</Text>
                </Table.Td>
                {/* P/L */}
                <Table.Td style={{ textAlign: 'right' }}>
                  <Text c={getVariationColor(p.unrealized_pl)} fw={500} size="sm">
                    {formatMoney(p.unrealized_pl, currency, true)}
                  </Text>
                </Table.Td>
                {/* P/L % */}
                <Table.Td style={{ textAlign: 'right' }}>
                  <Text c={getVariationColor(p.unrealized_pl_pct)} fw={500} size="sm">
                    {formatPct(p.unrealized_pl_pct)}
                  </Text>
                </Table.Td>
                {/* Allocazione */}
                <Table.Td style={{ textAlign: 'right' }}>
                  <Group gap="xs" wrap="nowrap" justify="flex-end">
                    <Progress value={p.weight} size="sm" w={60} color="blue" visibleFrom="sm" />
                    <Text size="xs">{p.weight.toFixed(1)}%</Text>
                  </Group>
                </Table.Td>
                {/* Prima Op. */}
                <Table.Td style={{ textAlign: 'right' }} visibleFrom="md">
                  <Text size="sm">{formatFirstTrade(p.first_trade_at)}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
            {/* Summary footer row */}
            <Table.Tr style={{ fontWeight: 700, borderTop: '2px solid var(--mantine-color-dark-4)' }}>
              <Table.Td>
                <Text fw={700} size="sm">TOTALE</Text>
              </Table.Td>
              <Table.Td visibleFrom="sm" />
              <Table.Td style={{ textAlign: 'right' }}>
                <Text fw={700} size="sm">{formatMoney(totals.totalValue, currency)}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text fw={700} size="sm" c={getVariationColor(totals.totalPl)}>
                  {formatMoney(totals.totalPl, currency, true)}
                </Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text fw={700} size="sm" c={getVariationColor(totals.totalPlPct)}>
                  {formatPct(totals.totalPlPct)}
                </Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text fw={700} size="xs">100%</Text>
              </Table.Td>
              <Table.Td visibleFrom="md" />
            </Table.Tr>
          </>
        ) : (
          <Table.Tr>
            <Table.Td colSpan={7}>
              <Text c="dimmed" ta="center" size="sm">Nessuna posizione disponibile</Text>
            </Table.Td>
          </Table.Tr>
        )}
      </Table.Tbody>
    </Table>
    </Table.ScrollContainer>
  );
}
