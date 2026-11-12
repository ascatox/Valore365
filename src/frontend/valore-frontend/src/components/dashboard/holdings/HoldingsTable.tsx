import React, { useState, useMemo } from 'react';
import { Badge, Card, Group, Progress, Table, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { useIsMobile } from '../../../hooks/useIsMobile';
import { IconChevronUp, IconChevronDown, IconSelector, IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import type { Position, PortfolioSummary } from '../../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';
import { AssetInfoModal } from './AssetInfoModal';
import { MobileHoldingsCards } from '../../mobile/MobileHoldingsCards';
import { TARGET_DRIFT_BASIS, formatDriftPoints, isDriftWarning, type TargetDriftMap } from './targetDrift';

type SortKey = 'symbol' | 'quantity' | 'market_price' | 'market_value' | 'unrealized_pl' | 'unrealized_pl_pct' | 'day_change_pct' | 'weight' | 'first_trade_at';

interface HoldingsTableProps {
  positions: Position[];
  currency: string;
  summary?: PortfolioSummary | null;
  /** Target and drift per asset (backend, same values as the Copilot); absent in the aggregate view. */
  targetMap?: TargetDriftMap;
  onRefreshPrices?: () => Promise<void>;
  refreshing?: boolean;
  /** Text when there are no positions (the aggregate view names the selected portfolios). */
  emptyMessage?: string;
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
  { label: 'Focus', key: 'symbol' as SortKey, align: 'left', visibleFrom: 'md', sortable: false },
  { label: 'Qta', key: 'quantity', align: 'right', visibleFrom: 'sm', sortable: true },
  { label: 'Prezzo Mkt', key: 'market_price', align: 'right', visibleFrom: 'sm', sortable: true },
  { label: 'Valore', key: 'market_value', align: 'right', sortable: true },
  { label: 'P/L', key: 'unrealized_pl', align: 'right', sortable: true },
  { label: 'P/L %', key: 'unrealized_pl_pct', align: 'right', sortable: true },
  { label: 'Var. Giorn.', key: 'day_change_pct', align: 'right', sortable: true },
  { label: 'Peso Titolo', key: 'weight', align: 'right', sortable: true },
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
    case 'day_change_pct': return p.day_change_pct;
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

export function HoldingsTable({ positions, currency, summary, targetMap, onRefreshPrices, refreshing, emptyMessage = 'Nessuna posizione disponibile' }: HoldingsTableProps) {
  const hasTargets = targetMap && targetMap.size > 0;
  const [sortKey, setSortKey] = useState<SortKey>('market_value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [infoModal, setInfoModal] = useState<{ assetId: number; symbol: string } | null>(null);
  const isMobile = useIsMobile();

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
        <Text c="dimmed" ta="center" size="sm">{emptyMessage}</Text>
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
          onRefreshPrices={onRefreshPrices}
          refreshing={refreshing}
        />
      </div>

      <Table.ScrollContainer minWidth={500} visibleFrom="sm">
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {BASE_COLUMNS.map((col) => (
                <React.Fragment key={col.label}>
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
                      <Tooltip label={TARGET_DRIFT_BASIS} withArrow multiline w={260}>
                        <Group gap={4} wrap="nowrap" justify="flex-end" style={{ display: 'inline-flex' }}>
                          <Text fw={600} size="xs" component="span">Target</Text>
                          <IconInfoCircle size={13} stroke={1.5} style={{ opacity: 0.5 }} aria-label="Base dello scostamento" />
                        </Group>
                      </Tooltip>
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
                      <Text fw={500} size="sm" lineClamp={1}>{p.name}</Text>
                      <StaleIcon position={p} />
                    </Group>
                    <Text size="xs" c="dimmed">{p.symbol}</Text>
                  </Table.Td>
                  <Table.Td visibleFrom="md">
                    {p.investment_focus ? (
                      <Badge size="xs" variant="light" color="gray">{p.investment_focus}</Badge>
                    ) : (
                      <Text size="xs" c="dimmed">—</Text>
                    )}
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
                    <Text c={getVariationColor(p.day_change_pct)} fw={500} size="sm">
                      {formatPct(p.day_change_pct)}
                    </Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Group gap="xs" wrap="nowrap" justify="flex-end">
                      <Progress value={p.weight} size="sm" w={60} color="teal" visibleFrom="sm" />
                      <Text size="xs">{formatNum(p.weight, 1)}%</Text>
                    </Group>
                  </Table.Td>
                  {hasTargets && (
                    <Table.Td style={{ textAlign: 'right' }}>
                      {(() => {
                        const item = targetMap.get(p.asset_id);
                        if (item == null) return <Text size="xs" c="dimmed">—</Text>;
                        const warn = isDriftWarning(item.drift_pct);
                        const label = `${formatDriftPoints(item.drift_pct)} dal target (peso ${formatNum(item.current_weight_pct, 2)}%). ${TARGET_DRIFT_BASIS}`;
                        return (
                          <Tooltip label={label} withArrow multiline w={280}>
                            <div>
                              <Group gap={4} wrap="nowrap" justify="flex-end">
                                <Text size="xs">{formatNum(item.target_weight_pct, 1)}%</Text>
                                {warn && (
                                  <IconAlertTriangle size={14} color="var(--mantine-color-orange-6)" style={{ flexShrink: 0 }} aria-label="Scostamento oltre 5 punti" />
                                )}
                              </Group>
                              <Text size="xs" fw={warn ? 700 : 500} c={warn ? 'orange' : 'dimmed'} data-testid={`target-drift-${p.asset_id}`}>
                                {formatDriftPoints(item.drift_pct)}
                              </Text>
                            </div>
                          </Tooltip>
                        );
                      })()}
                    </Table.Td>
                  )}
                  <Table.Td style={{ textAlign: 'right' }} visibleFrom="md">
                    <Text size="sm">{formatFirstTrade(p.first_trade_at)}</Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'center' }}>
                    <Tooltip label="Dettaglio asset" withArrow>
                      <UnstyledButton
                        onClick={() => setInfoModal({ assetId: p.asset_id, symbol: p.symbol })}
                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 36, minHeight: 36, borderRadius: 8 }}
                      >
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
                <Table.Td visibleFrom="md" />
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
                  {summary?.day_change_pct != null && (
                    <Text fw={700} size="sm" c={getVariationColor(summary.day_change_pct)}>
                      {formatPct(summary.day_change_pct)}
                    </Text>
                  )}
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
