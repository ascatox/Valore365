import { useMemo } from 'react';
import { Alert, Card, Group, Loader, Paper, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { IconTrendingDown, IconTrendingUp } from '@tabler/icons-react';
import { formatDateTime, formatPct, getVariationColor } from '../formatters';
import { useMarketQuotes } from '../hooks/queries';
import type { MarketQuoteItem } from '../../../services/api';

const formatMarketPrice = (value: number | null) => {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  const abs = Math.abs(value);
  const decimals = abs >= 1000 ? 2 : abs >= 1 ? 2 : 4;
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
};

function IntradayMiniChart({ item }: { item: MarketQuoteItem }) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const data = item.intraday;
  if (!data || data.length < 2) return null;

  const variation = item.change_pct;
  const color = variation != null && variation < 0 ? '#dc2626' : '#16a34a';

  return (
    <div style={{ height: 80, marginTop: 4 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id={`mktGrad-${item.symbol}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.15} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            axisLine={false}
            tickLine={false}
            tick={{ fill: tickColor, fontSize: 9 }}
            interval="preserveStartEnd"
            tickFormatter={(v: string) => v.split(' ')[0]}
          />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip
            content={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const val = Number(payload[0]?.value ?? 0);
              return (
                <Paper withBorder p={4} radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{label}</Text>
                  <Text size="xs" fw={600}>{formatMarketPrice(val)}</Text>
                </Paper>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={color}
            strokeWidth={1.5}
            fillOpacity={1}
            fill={`url(#mktGrad-${item.symbol})`}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function MarketItemCard({ item }: { item: MarketQuoteItem }) {
  const variation = item.change_pct;
  const variationColor = variation != null ? getVariationColor(variation) : 'gray';
  const isError = !!item.error;

  return (
    <Card withBorder radius="md" shadow="sm" style={{ opacity: isError ? 0.75 : 1 }}>
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <div>
            <Text fw={600}>{item.name}</Text>
            <Text size="xs" c="dimmed">{item.symbol}</Text>
          </div>
          <ThemeIcon
            color={variation != null ? variationColor : 'gray'}
            variant="light"
            radius="xl"
            aria-label="Trend"
          >
            {variation != null && variation < 0 ? <IconTrendingDown size={16} /> : <IconTrendingUp size={16} />}
          </ThemeIcon>
        </Group>

        <Text fw={700} size="lg">{formatMarketPrice(item.price)}</Text>

        <Group justify="space-between" gap="xs">
          <Text size="sm" c={variationColor} fw={600}>
            {variation != null ? formatPct(variation) : 'N/D'}
          </Text>
          <Text size="xs" c="dimmed">
            {item.ts ? formatDateTime(item.ts) : 'N/D'}
          </Text>
        </Group>

        <IntradayMiniChart item={item} />

        {item.error && (
          <Text size="xs" c="red">
            {item.error}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function MercatiTab() {
  const { data, isLoading, error } = useMarketQuotes();

  const lastUpdatedAt = useMemo(() => {
    if (!data) return null;
    let latestTs: string | null = null;
    for (const cat of data.categories) {
      for (const item of cat.items) {
        if (item.ts && (!latestTs || item.ts > latestTs)) {
          latestTs = item.ts;
        }
      }
    }
    return latestTs;
  }, [data]);

  if (isLoading && !data) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Caricamento quotazioni di mercato...</Text>
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <Text size="xs" c="dimmed">
        Ultimo aggiornamento: {lastUpdatedAt ? formatDateTime(lastUpdatedAt) : 'N/D'}
      </Text>

      {error && <Alert color="red">{error instanceof Error ? error.message : 'Errore caricamento mercati'}</Alert>}

      {!isLoading && !data && !error && (
        <Text size="sm" c="dimmed">Nessun dato di mercato disponibile.</Text>
      )}

      {data?.categories.map((category) => (
        <Card key={category.category} withBorder radius="md" p="md" shadow="sm">
          <Text fw={700} mb="md">{category.label}</Text>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
            {category.items.map((item) => (
              <MarketItemCard key={item.symbol} item={item} />
            ))}
          </SimpleGrid>
        </Card>
      ))}
    </Stack>
  );
}
