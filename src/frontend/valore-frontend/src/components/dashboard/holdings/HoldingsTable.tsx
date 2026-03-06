import React, { useState, useMemo } from 'react';
import { Card, Group, Progress, Stack, Table, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconChevronUp, IconChevronDown, IconSelector, IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import type { Position, PortfolioSummary } from '../../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';
import { AssetInfoModal } from './AssetInfoModal';
import { MobileHoldingsCards } from '../../mobile/MobileHoldingsCards';

type SortKey = 'symbol' | 'quantity' | 'market_price' | 'market_value' | 'unrealized_pl' | 'unrealized_pl_pct' | 'weight' | 'first_trade_at';

interface HoldingsTableProps {
  positions: Position[];
  currency: string;
  summary?: PortfolioSummary | null;
  targetMap?: Map<number, number>;
}

interface ColumnDef {
  label: string;
  key: SortKey;
  align: 'left' | 'right';
  visibleFrom?: 'sm' | 'md';
  sortable: boolean;
}

const BASE_COLUMNS: ColumnDef[] = [
  { label: 'Asset', key: 'symbol', align: 'left', sortable: true },
  { label: 'Qta', key: 'quantity', align: 'right', visibleFrom: 'sm', sortable: true },
  { label: 'Prezzo Mkt', key: 'market_price', align: 'right', visibleFrom: 'sm', sortable: true },
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
    case 'market_price': return p.market_price;
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

function formatPriceDate(value?: string | null): string {
  if (!value) return 'N/D';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return 'N/D';
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function StaleIcon({ position }: { position: Position }) {
  if (!position.price_stale) return null;
  const label = `Prezzo non aggiornato${position.price_date ? ` (ultimo: ${formatPriceDate(position.price_date)})` : ''}`;
  return (
    <Tooltip label={label} withArrow>
      <IconAlertTriangle size={14} color="var(--mantine-color-yellow-6)" style={{ flexShrink: 0 }} />
    </Tooltip>
  );
}

export function HoldingsTable({ positions, currency, summary, targetMap }: HoldingsTableProps) {
  const hasTargets = targetMap && targetMap.size > 0;
  const [sortKey, setSortKey] = useState<SortKey>('market_value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [infoModal, setInfoModal] = useState<{ assetId: number; symbol: string } | null>(null);
  const isMobile = useMediaQuery('(max-width: 48em)');

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

  if (!sorted.length) {
    return (
      <Card withBorder>
        <Text c="dimmed" ta="center" size="sm">Nessuna posizione disponibile</Text>
      </Card>
    );
  }

  return (
    <>
      {!isMobile && infoModal && (
        <AssetInfoModal
          assetId={infoModal.assetId}
          symbol={infoModal.symbol}
          opened={!!infoModal}
          onClose={() => setInfoModal(null)}
        />
      )}

      <div hidden={!isMobile}>
        <MobileHoldingsCards
          positions={sorted}
          currency={currency}
          summary={summary}
          targetMap={targetMap}
        />
      </div>

      <Table.ScrollContainer minWidth={500} visibleFrom="sm">
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {BASE_COLUMNS.map((col) => (
                <React.Fragment key={col.key}>
                  <Table.Th
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
                  {col.key === 'weight' && hasTargets && (
                    <Table.Th style={{ textAlign: 'right' }}>
                      <Text fw={600} size="xs" component="span">Target</Text>
                    </Table.Th>
                  )}
                </React.Fragment>
              ))}
              <Table.Th style={{ width: 36 }} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <>
              {sorted.map((p) => (
                <Table.Tr key={p.asset_id}>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Text fw={500} size="sm">{p.symbol}</Text>
                      <StaleIcon position={p} />
                    </Group>
                    <Text size="xs" c="dimmed" lineClamp={1}>{p.name}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">
                    <Text size="sm">{formatNum(p.quantity)}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">
                    <Text size="sm">{formatMoney(p.market_price, currency)}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Text size="sm">{formatMoney(p.market_value, currency)}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Text c={getVariationColor(p.unrealized_pl)} fw={500} size="sm">
                      {formatMoney(p.unrealized_pl, currency, true)}
                    </Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Text c={getVariationColor(p.unrealized_pl_pct)} fw={500} size="sm">
                      {formatPct(p.unrealized_pl_pct)}
                    </Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Group gap="xs" wrap="nowrap" justify="flex-end">
                      <Progress value={p.weight} size="sm" w={60} color="blue" visibleFrom="sm" />
                      <Text size="xs">{formatNum(p.weight, 1)}%</Text>
                    </Group>
                  </Table.Td>
                  {hasTargets && (
                    <Table.Td style={{ textAlign: 'right' }}>
                      {(() => {
                        const target = targetMap.get(p.asset_id);
                        if (target == null) return <Text size="xs" c="dimmed">—</Text>;
                        const delta = p.weight - target;
                        const warn = Math.abs(delta) > 5;
                        return (
                          <Group gap={4} wrap="nowrap" justify="flex-end">
                            <Text size="xs">{formatNum(target, 1)}%</Text>
                            {warn && (
                              <Tooltip label={`Scostamento: ${delta > 0 ? '+' : ''}${formatNum(delta, 1)}%`} withArrow>
                                <IconAlertTriangle size={14} color="var(--mantine-color-orange-6)" style={{ flexShrink: 0 }} />
                              </Tooltip>
                            )}
                          </Group>
                        );
                      })()}
                    </Table.Td>
                  )}
                  <Table.Td style={{ textAlign: 'right' }} visibleFrom="md">
                    <Text size="sm">{formatFirstTrade(p.first_trade_at)}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'center' }}>
                    <Tooltip label="Dettaglio asset" withArrow>
                      <UnstyledButton onClick={() => setInfoModal({ assetId: p.asset_id, symbol: p.symbol })}>
                        <IconInfoCircle size={16} stroke={1.5} style={{ opacity: 0.5 }} />
                      </UnstyledButton>
                    </Tooltip>
                  </Table.Td>
                </Table.Tr>
              ))}
              <Table.Tr style={{ fontWeight: 700, borderTop: '2px solid var(--mantine-color-dark-4)' }}>
                <Table.Td>
                  <Text fw={700} size="sm">TOTALE</Text>
                </Table.Td>
                <Table.Td visibleFrom="sm" />
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
                {hasTargets && <Table.Td />}
                <Table.Td visibleFrom="md" />
                <Table.Td />
              </Table.Tr>
            </>
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </>
  );
}
