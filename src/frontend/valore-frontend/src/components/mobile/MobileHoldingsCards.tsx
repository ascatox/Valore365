import { useMemo, useState } from 'react';
import { Badge, Box, Button, Chip, Group, SimpleGrid, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react';
import type { Position, PortfolioSummary } from '../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../dashboard/formatters';
import { BottomSheet } from './BottomSheet';
import { TARGET_DRIFT_BASIS, formatDriftPoints, isDriftWarning, type TargetDriftMap } from '../dashboard/holdings/targetDrift';

interface MobileHoldingsCardsProps {
  positions: Position[];
  currency: string;
  summary?: PortfolioSummary | null;
  /** Target and drift per asset (backend, same values as the Copilot). */
  targetMap?: TargetDriftMap;
  onRefreshPrices?: () => Promise<void>;
  refreshing?: boolean;
}

type SortKey = 'value' | 'day' | 'pl' | 'drift';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'value', label: 'Valore' },
  { value: 'day', label: 'Oggi' },
  { value: 'pl', label: 'P/L' },
  { value: 'drift', label: 'Scostamento' },
];

type AssetClass = 'equity' | 'bond' | 'gold' | 'cash' | 'crypto';

const ASSET_CLASS_COLORS: Record<AssetClass, string> = {
  equity: 'var(--mantine-color-teal-6)',
  bond: '#47607a',
  gold: '#b08a2e',
  cash: '#7a8786',
  crypto: 'var(--mantine-color-grape-6)',
};

function assetClassOf(position: Position): AssetClass {
  const focus = `${position.investment_focus ?? ''} ${position.name ?? ''}`.toLowerCase();
  if (position.asset_type === 'crypto') return 'crypto';
  if (position.asset_type === 'cash' || /money market|overnight|monetar|cash/.test(focus)) return 'cash';
  if (position.asset_type === 'bond' || /bond|fixed income|obbligaz|aggregate|treasury/.test(focus)) return 'bond';
  if (/gold|oro|commodit|precious/.test(focus)) return 'gold';
  return 'equity';
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function MobileHoldingsCards({ positions, currency, summary, targetMap, onRefreshPrices, refreshing }: MobileHoldingsCardsProps) {
  const [sortKey, setSortKey] = useState<SortKey>('value');
  // The id, not the row: the sheet then shows the refreshed values after
  // "Aggiorna prezzi" refetches the positions.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = selectedId != null ? positions.find((p) => p.asset_id === selectedId) ?? null : null;
  const hasTargets = !!targetMap && targetMap.size > 0;

  // Drift from the backend (TASK-88): on targeted holdings + cash, as the Copilot
  // and the rebalancing, so the bar of a targeted row uses that weight too.
  const drift = (position: Position) => targetMap?.get(position.asset_id)?.drift_pct ?? null;

  const sorted = useMemo(() => {
    const value = (p: Position) => {
      switch (sortKey) {
        case 'day': return p.day_change_pct;
        case 'pl': return p.unrealized_pl;
        case 'drift': {
          const item = targetMap?.get(p.asset_id);
          return item != null ? Math.abs(item.drift_pct) : -1;
        }
        default: return p.market_value;
      }
    };
    return [...positions].sort((a, b) => value(b) - value(a));
  }, [positions, sortKey, targetMap]);

  const totals = useMemo(() => {
    const totalValue = summary?.market_value ?? positions.reduce((sum, p) => sum + p.market_value, 0);
    const totalPlPct = summary?.unrealized_pl_pct ?? 0;
    return { totalValue, totalPlPct };
  }, [positions, summary]);

  if (!positions.length) {
    return <Text c="dimmed" ta="center" size="sm" py="md">Nessuna posizione disponibile</Text>;
  }

  const selectedDrift = selected ? drift(selected) : null;
  const selectedTarget = selected ? targetMap?.get(selected.asset_id) : undefined;

  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm" c="dimmed">{`Totale ${formatMoney(totals.totalValue, currency)}`}</Text>
        <Text size="sm" fw={700} c={getVariationColor(totals.totalPlPct)}>{formatPct(totals.totalPlPct)}</Text>
      </Group>

      <Chip.Group value={sortKey} onChange={(value) => setSortKey(value as SortKey)}>
        <Group gap={6} wrap="nowrap" style={{ overflowX: 'auto', scrollbarWidth: 'none' }}>
          {SORT_OPTIONS.filter((option) => option.value !== 'drift' || hasTargets).map((option) => (
            <Chip key={option.value} value={option.value} size="sm" variant="outline">
              {option.label}
            </Chip>
          ))}
        </Group>
      </Chip.Group>

      <Box>
        {sorted.map((position, index) => {
          const item = targetMap?.get(position.asset_id);
          const target = item?.target_weight_pct;
          const delta = drift(position);
          const warn = isDriftWarning(delta);
          // Targeted row: weight on the drift base, so bar, marker and points agree.
          const barWeight = item ? item.current_weight_pct : position.weight;
          const assetClass = assetClassOf(position);
          return (
            <UnstyledButton
              key={position.asset_id}
              onClick={() => setSelectedId(position.asset_id)}
              aria-label={`Dettagli ${position.symbol}`}
              style={{
                display: 'block',
                width: '100%',
                padding: '10px 0',
                borderTop: index === 0 ? undefined : '1px solid var(--mantine-color-default-border)',
              }}
            >
              <Group gap={10} wrap="nowrap" align="center">
                <Box
                  style={{
                    width: '2.25rem',
                    height: '2.25rem',
                    flexShrink: 0,
                    borderRadius: 10,
                    display: 'grid',
                    placeItems: 'center',
                    background: ASSET_CLASS_COLORS[assetClass],
                    color: '#ffffff',
                    fontSize: '0.625rem',
                    fontWeight: 800,
                    letterSpacing: 0.2,
                  }}
                >
                  {position.symbol.slice(0, 4)}
                </Box>
                <Box style={{ minWidth: 0, flex: 1 }}>
                  <Group gap={4} wrap="nowrap">
                    <Text fw={700} size="sm">{position.symbol}</Text>
                    {position.price_stale && <IconAlertTriangle size={14} color="var(--mantine-color-orange-text)" aria-label="Prezzo non aggiornato" />}
                  </Group>
                  <Text size="xs" c="dimmed" truncate="end">{position.name || position.symbol}</Text>
                </Box>
                <Box style={{ textAlign: 'right', flexShrink: 0 }}>
                  <Text fw={700} size="sm">{formatMoney(position.market_value, currency)}</Text>
                  <Text size="xs" fw={600} c={getVariationColor(sortKey === 'day' ? position.day_change_pct : position.unrealized_pl)}>
                    {sortKey === 'day'
                      ? `${formatPct(position.day_change_pct)} oggi`
                      : `${formatMoney(position.unrealized_pl, currency, true)} (${formatPct(position.unrealized_pl_pct)})`}
                  </Text>
                </Box>
              </Group>

              <Box ml={46} mt={8}>
                <Box style={{ position: 'relative', height: 4, borderRadius: 2, background: 'var(--mantine-color-default-border)' }}>
                  <Box
                    style={{
                      position: 'absolute',
                      inset: '0 auto 0 0',
                      width: `${Math.min(100, Math.max(0, barWeight))}%`,
                      borderRadius: 2,
                      background: warn ? 'var(--mantine-color-orange-filled)' : 'var(--mantine-primary-color-filled)',
                    }}
                  />
                  {target != null && (
                    <Box
                      aria-hidden
                      style={{
                        position: 'absolute',
                        top: -3,
                        left: `calc(${Math.min(100, target)}% - 1px)`,
                        width: 2,
                        height: 10,
                        borderRadius: 1,
                        background: 'var(--mantine-color-text)',
                      }}
                    />
                  )}
                </Box>
                <Group justify="space-between" mt={4} wrap="nowrap">
                  <Text size="xs" c="dimmed">
                    {item ? `${formatNum(item.current_weight_pct, 1)}% · target ${formatNum(item.target_weight_pct, 0)}%` : `${formatNum(position.weight, 1)}% del portafoglio`}
                  </Text>
                  {delta != null && (
                    <Text size="xs" fw={warn ? 700 : 500} c={warn ? 'orange' : 'dimmed'}>
                      {formatDriftPoints(delta)}
                    </Text>
                  )}
                </Group>
              </Box>
            </UnstyledButton>
          );
        })}
      </Box>

      {hasTargets && (
        <Text size="xs" c="dimmed">Peso e scostamento delle righe con target: sul valore degli strumenti con target più la liquidità, come nel ribilanciamento e nel Copilot.</Text>
      )}

      <BottomSheet
        opened={!!selected}
        onClose={() => setSelectedId(null)}
        title={selected ? selected.symbol : ''}
      >
        {selected && (
          <Stack gap="md">
            <Text size="sm" c="dimmed">{selected.name}</Text>
            {selected.price_stale && (
              <Badge color="orange" variant="light" leftSection={<IconAlertTriangle size={12} />} style={{ alignSelf: 'flex-start' }}>
                {`Prezzo non aggiornato${selected.price_date ? ` · ultimo ${formatDate(selected.price_date)}` : ''}`}
              </Badge>
            )}
            <SimpleGrid cols={2} spacing="md" verticalSpacing="sm">
              <Detail label="Valore" value={formatMoney(selected.market_value, currency)} />
              <Detail
                label="P/L"
                value={`${formatMoney(selected.unrealized_pl, currency, true)} (${formatPct(selected.unrealized_pl_pct)})`}
                color={getVariationColor(selected.unrealized_pl)}
              />
              <Detail label="Oggi" value={formatPct(selected.day_change_pct)} color={getVariationColor(selected.day_change_pct)} />
              <Detail label="Peso" value={`${formatNum(selected.weight, 1)}% delle posizioni`} />
              {selectedTarget != null && selectedDrift != null && (
                <Detail
                  label="Vs target"
                  value={`${formatDriftPoints(selectedDrift)} (target ${formatNum(selectedTarget.target_weight_pct, 0)}%)`}
                  color={isDriftWarning(selectedDrift) ? 'orange' : undefined}
                />
              )}
              <Detail label="Quantità" value={formatNum(selected.quantity, 4)} />
              <Detail label="Prezzo" value={formatMoney(selected.market_price, currency)} />
              <Detail label="Prezzo medio" value={formatMoney(selected.avg_cost, currency)} />
              <Detail label="Prima operazione" value={formatDate(selected.first_trade_at)} />
            </SimpleGrid>
            {selectedTarget != null && (
              <Text size="xs" c="dimmed">{TARGET_DRIFT_BASIS}</Text>
            )}
            {onRefreshPrices && (
              <Button
                variant="light"
                leftSection={<IconRefresh size={16} />}
                loading={refreshing}
                onClick={onRefreshPrices}
              >
                Aggiorna prezzi
              </Button>
            )}
          </Stack>
        )}
      </BottomSheet>
    </Stack>
  );
}

function Detail({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Box>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.6 }}>{label}</Text>
      <Text fw={700} size="sm" c={color}>{value}</Text>
    </Box>
  );
}
