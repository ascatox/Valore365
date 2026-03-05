import { useEffect, useState, useMemo } from 'react';
import { Card, Grid, Group, Loader, Modal, Paper, Progress, Stack, Table, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { IconChevronUp, IconChevronDown, IconSelector, IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import type { AssetInfo, Position, PortfolioSummary } from '../../../services/api';
import { getAssetInfo } from '../../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';

type SortKey = 'symbol' | 'quantity' | 'market_price' | 'market_value' | 'unrealized_pl' | 'unrealized_pl_pct' | 'weight' | 'first_trade_at';

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

function formatMarketCap(value: number | null): string {
  if (value == null) return 'N/D';
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return formatNum(value, 0);
}

function formatVolume(value: number | null): string {
  if (value == null) return 'N/D';
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return formatNum(value, 0);
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <Group justify="space-between" gap="xs">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Group>
  );
}

function PriceHistoryChart({ data, currency }: { data: { date: string; close: number }[]; currency: string | null }) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const chartData = useMemo(() =>
    data.map((p) => ({
      date: new Date(p.date).toLocaleDateString('it-IT', { month: '2-digit', year: '2-digit' }),
      close: p.close,
      rawDate: p.date,
    })),
    [data],
  );

  const first = data[0]?.close ?? 0;
  const last = data[data.length - 1]?.close ?? 0;
  const changePct = first > 0 ? ((last / first) - 1) * 100 : 0;
  const color = changePct >= 0 ? '#16a34a' : '#dc2626';

  return (
    <Stack gap={4}>
      <Group justify="space-between" gap="xs">
        <Text size="xs" fw={600}>Storico 5 anni</Text>
        <Text size="xs" fw={600} c={changePct >= 0 ? 'green' : 'red'}>
          {changePct >= 0 ? '+' : ''}{formatNum(changePct, 1)}%
        </Text>
      </Group>
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="assetInfoGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
            <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis hide domain={['auto', 'auto']} />
            <RechartsTooltip
              content={({ active, payload, label }: any) => {
                if (!active || !payload?.length) return null;
                const val = Number(payload[0]?.value ?? 0);
                return (
                  <Paper withBorder p="xs" radius="sm" shadow="xs">
                    <Text size="xs" c="dimmed">{label}</Text>
                    <Text size="sm" fw={600}>{formatMoney(val, currency ?? 'USD')}</Text>
                  </Paper>
                );
              }}
            />
            <Area type="monotone" dataKey="close" stroke={color} strokeWidth={1.5} fillOpacity={1} fill="url(#assetInfoGrad)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Stack>
  );
}

function AssetInfoModal({ assetId, symbol, opened, onClose }: { assetId: number; symbol: string; opened: boolean; onClose: () => void }) {
  const [info, setInfo] = useState<AssetInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!opened) return;
    let active = true;
    setLoading(true);
    setError(null);
    setInfo(null);
    getAssetInfo(assetId)
      .then((data) => { if (active) setInfo(data); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : 'Errore nel caricamento'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [opened, assetId]);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="xs">
          <IconInfoCircle size={20} />
          <Text fw={600}>Dettaglio {symbol}</Text>
        </Group>
      }
      size="md"
      centered
    >
      {loading && (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text c="dimmed" size="sm">Caricamento informazioni...</Text>
        </Group>
      )}
      {error && (
        <Text c="red" size="sm" ta="center" py="xl">{error}</Text>
      )}
      {info && !loading && (
        <Stack gap="md">
          {info.name && <Text fw={600} size="md">{info.name}</Text>}

          <Grid gutter="md">
            <Grid.Col span={6}>
              <Stack gap={6}>
                {info.sector && <InfoRow label="Settore" value={info.sector} />}
                {info.industry && <InfoRow label="Industria" value={info.industry} />}
                {info.country && <InfoRow label="Paese" value={info.country} />}
                {info.currency && <InfoRow label="Valuta" value={info.currency} />}
              </Stack>
            </Grid.Col>
            <Grid.Col span={6}>
              <Stack gap={6}>
                <InfoRow label="Market Cap" value={formatMarketCap(info.market_cap)} />
                {info.trailing_pe != null && <InfoRow label="P/E (TTM)" value={formatNum(info.trailing_pe)} />}
                {info.forward_pe != null && <InfoRow label="P/E (Fwd)" value={formatNum(info.forward_pe)} />}
                {info.dividend_yield != null && <InfoRow label="Div. Yield" value={formatPct(info.dividend_yield * 100)} />}
                {info.beta != null && <InfoRow label="Beta" value={formatNum(info.beta)} />}
                <InfoRow label="Vol. Medio" value={formatVolume(info.avg_volume)} />
              </Stack>
            </Grid.Col>
          </Grid>

          {info.price_history_5y.length > 0 && (
            <PriceHistoryChart data={info.price_history_5y} currency={info.currency} />
          )}

          {info.description && (
            <Text size="xs" c="dimmed" lineClamp={6} style={{ lineHeight: 1.5 }}>
              {info.description}
            </Text>
          )}
        </Stack>
      )}
    </Modal>
  );
}

export function HoldingsTable({ positions, currency, summary }: HoldingsTableProps) {
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

      <Stack gap="sm" hiddenFrom="sm">
        {sorted.map((p) => (
          <Card key={p.asset_id} withBorder>
            <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
              <div>
                <Group gap={4} wrap="nowrap">
                  <Text fw={600} size="sm">{p.symbol}</Text>
                  <StaleIcon position={p} />
                </Group>
                <Text size="xs" c="dimmed" lineClamp={1}>{p.name}</Text>
              </div>
              <Text fw={700} size="sm">{formatMoney(p.market_value, currency)}</Text>
            </Group>

            <Group justify="space-between" mt="sm" gap="xs">
              <Text size="sm" c="dimmed">Quantita</Text>
              <Text size="sm">{formatNum(p.quantity)}</Text>
            </Group>
            <Group justify="space-between" gap="xs">
              <Text size="sm" c="dimmed">P/L</Text>
              <Text size="sm" fw={600} c={getVariationColor(p.unrealized_pl)}>
                {formatMoney(p.unrealized_pl, currency, true)}
              </Text>
            </Group>
            <Group justify="space-between" gap="xs">
              <Text size="sm" c="dimmed">Prezzo Mkt</Text>
              <Text size="sm">{formatMoney(p.market_price, currency)}</Text>
            </Group>
            <Group justify="space-between" gap="xs">
              <Text size="sm" c="dimmed">P/L %</Text>
              <Text size="sm" fw={600} c={getVariationColor(p.unrealized_pl_pct)}>
                {formatPct(p.unrealized_pl_pct)}
              </Text>
            </Group>
            <Group justify="space-between" align="center" gap="xs" mt={4}>
              <Text size="sm" c="dimmed">Allocazione</Text>
              <Group gap="xs" wrap="nowrap">
                <Progress value={p.weight} size="sm" w={80} color="blue" />
                <Text size="xs">{formatNum(p.weight, 1)}%</Text>
              </Group>
            </Group>
            <Group justify="space-between" gap="xs" mt={4}>
              <Text size="sm" c="dimmed">Prima operazione</Text>
              <Text size="sm">{formatFirstTrade(p.first_trade_at)}</Text>
            </Group>
          </Card>
        ))}

        <Card withBorder>
          <Group justify="space-between" gap="xs">
            <Text fw={700}>Totale</Text>
            <Text fw={700}>{formatMoney(totals.totalValue, currency)}</Text>
          </Group>
          <Group justify="space-between" gap="xs" mt={4}>
            <Text size="sm" c="dimmed">P/L</Text>
            <Text size="sm" fw={700} c={getVariationColor(totals.totalPl)}>
              {formatMoney(totals.totalPl, currency, true)}
            </Text>
          </Group>
          <Group justify="space-between" gap="xs">
            <Text size="sm" c="dimmed">P/L %</Text>
            <Text size="sm" fw={700} c={getVariationColor(totals.totalPlPct)}>
              {formatPct(totals.totalPlPct)}
            </Text>
          </Group>
        </Card>
      </Stack>

      <Table.ScrollContainer minWidth={500} visibleFrom="sm">
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
