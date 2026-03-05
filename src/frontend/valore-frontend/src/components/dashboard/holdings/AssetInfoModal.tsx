import { useEffect, useState, useMemo } from 'react';
import { Badge, Grid, Group, Loader, Modal, Paper, Stack, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { IconInfoCircle } from '@tabler/icons-react';
import type { AssetInfo } from '../../../services/api';
import { getAssetInfo } from '../../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';

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

interface AssetInfoModalProps {
  assetId: number;
  symbol: string;
  opened: boolean;
  onClose: () => void;
}

export function AssetInfoModal({ assetId, symbol, opened, onClose }: AssetInfoModalProps) {
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

          {info.current_price != null && (
            <Group gap="sm" align="center">
              <Text fw={700} size="lg">{formatMoney(info.current_price, info.currency ?? 'USD')}</Text>
              {info.day_change_pct != null && (
                <Badge
                  variant="light"
                  color={getVariationColor(info.day_change_pct)}
                  size="lg"
                  styles={{ root: { fontSize: 14, fontWeight: 600 } }}
                >
                  {info.day_change_pct >= 0 ? '+' : ''}{formatPct(info.day_change_pct)}
                </Badge>
              )}
            </Group>
          )}

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
