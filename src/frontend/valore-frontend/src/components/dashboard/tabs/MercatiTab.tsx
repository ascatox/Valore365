import { useMemo, useState } from 'react';
import { Alert, Badge, Card, Group, Loader, Paper, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { IconAlertTriangle, IconTrendingDown, IconTrendingUp } from '@tabler/icons-react';
import { formatDateTime, formatPct, getVariationColor } from '../formatters';
import { useMarketQuotes } from '../hooks/queries';
import type { MarketQuoteItem } from '../../../services/api';
import { formatPriceSourceLabel, formatProviderWarning } from '../../../services/dataQuality';
import { AssetInfoModal } from '../holdings/AssetInfoModal';
import { MarketTicker } from './MarketTicker';
import { NewsTicker } from './NewsTicker';

/* ── Exchange schedule per symbol ────────────────────────────────── */

interface ExchangeSchedule {
  exchange: string;
  tz: string;          // IANA timezone
  openHour: number;    // 0-23
  openMin: number;
  closeHour: number;
  closeMin: number;
  weekdays: boolean;   // true = Mon-Fri only
}

const EXCHANGE_SCHEDULES: Record<string, ExchangeSchedule> = {
  // US indices
  '^GSPC':      { exchange: 'NYSE',      tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  '^DJI':       { exchange: 'NYSE',      tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  '^IXIC':      { exchange: 'NASDAQ',    tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  // European indices
  '^STOXX50E':  { exchange: 'Eurex',     tz: 'Europe/Berlin',     openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  'FTSEMIB.MI': { exchange: 'Borsa Italiana', tz: 'Europe/Rome',  openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  '^FTSE':      { exchange: 'LSE',       tz: 'Europe/London',     openHour: 8,  openMin: 0,  closeHour: 16, closeMin: 30, weekdays: true },
  '^GDAXI':     { exchange: 'XETRA',     tz: 'Europe/Berlin',     openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  // Japan
  '^N225':      { exchange: 'TSE',       tz: 'Asia/Tokyo',        openHour: 9,  openMin: 0,  closeHour: 15, closeMin: 0,  weekdays: true },
  // Commodities (CME futures: Sun 17:00 – Fri 16:00 CT, with daily break 16:00-17:00)
  'GC=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  'SI=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  'CL=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  // Crypto – always open
  'BTC-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
  'ETH-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
  'SOL-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
};

function isExchangeOpen(schedule: ExchangeSchedule, now: Date): boolean {
  // Crypto is always open
  if (!schedule.weekdays && schedule.openHour === 0 && schedule.closeHour === 0) return true;

  // Get current time in the exchange timezone
  const tzTime = new Date(now.toLocaleString('en-US', { timeZone: schedule.tz }));
  const day = tzTime.getDay(); // 0=Sun, 6=Sat
  const hour = tzTime.getHours();
  const min = tzTime.getMinutes();
  const timeInMin = hour * 60 + min;

  const openMin = schedule.openHour * 60 + schedule.openMin;
  const closeMin = schedule.closeHour * 60 + schedule.closeMin;

  // CME-style overnight session (open > close means session spans midnight)
  if (openMin > closeMin) {
    // Closed on Saturday all day; Sunday open from openHour; Friday close at closeHour
    if (day === 6) return false; // Saturday
    if (day === 0) return timeInMin >= openMin; // Sunday: open from 17:00
    if (day === 5) return timeInMin < closeMin; // Friday: close at 16:00
    // Mon-Thu: only closed during daily break (closeMin..openMin)
    return timeInMin >= openMin || timeInMin < closeMin;
  }

  // Standard session: weekdays only, open-close same day
  if (day === 0 || day === 6) return false;
  return timeInMin >= openMin && timeInMin < closeMin;
}

function getClosedReason(schedule: ExchangeSchedule, now: Date): string {
  const tzTime = new Date(now.toLocaleString('en-US', { timeZone: schedule.tz }));
  const day = tzTime.getDay();
  if (day === 0 || day === 6) return 'weekend';
  return 'orario di chiusura';
}

interface ClosedExchangeInfo {
  exchange: string;
  reason: string;
}

function getClosedExchanges(symbols: string[], now: Date): ClosedExchangeInfo[] {
  const seen = new Set<string>();
  const result: ClosedExchangeInfo[] = [];

  for (const symbol of symbols) {
    const schedule = EXCHANGE_SCHEDULES[symbol];
    if (!schedule || seen.has(schedule.exchange)) continue;
    seen.add(schedule.exchange);

    if (!isExchangeOpen(schedule, now)) {
      result.push({ exchange: schedule.exchange, reason: getClosedReason(schedule, now) });
    }
  }
  return result;
}

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

function MarketItemCard({ item, onClick }: { item: MarketQuoteItem; onClick?: () => void }) {
  const variation = item.change_pct;
  const variationColor = variation != null ? getVariationColor(variation) : 'gray';
  const isError = !!item.error;
  const dataWarning = formatProviderWarning(item.warning) ?? (item.stale ? 'Prezzo non realtime.' : null);

  return (
    <Card withBorder radius="sm" shadow="xs" p="sm" style={{ opacity: isError ? 0.75 : 1, cursor: 'pointer' }} onClick={onClick}>
      <Stack gap={4}>
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

        <Group gap={6} wrap="wrap">
          {item.is_fallback && (
            <Badge size="xs" variant="light" color="yellow">
              prezzo fallback
            </Badge>
          )}
          {item.stale && (
            <Badge size="xs" variant="light" color="orange">
              non realtime
            </Badge>
          )}
          {item.price_source && (
            <Badge size="xs" variant="outline" color="gray">
              {formatPriceSourceLabel(item.price_source)}
            </Badge>
          )}
        </Group>

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
        {!item.error && dataWarning && (
          <Text size="xs" c="dimmed">
            {dataWarning}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function MercatiTab() {
  const { data, isLoading, error } = useMarketQuotes();
  const [closedAlertDismissed, setClosedAlertDismissed] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

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

  const closedExchanges = useMemo(() => {
    if (!data) return [];
    const allSymbols = data.categories.flatMap((c) => c.items.map((i) => i.symbol));
    return getClosedExchanges(allSymbols, new Date());
  }, [data]);

  const degradedItems = useMemo(
    () => data?.categories.flatMap((category) => category.items).filter((item) => item.stale || item.is_fallback) ?? [],
    [data],
  );

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
      <MarketTicker />
      <NewsTicker />

      {closedExchanges.length > 0 && !closedAlertDismissed && (
        <Alert
          color="yellow"
          icon={<IconAlertTriangle size={18} />}
          title="Alcune borse sono attualmente chiuse"
          withCloseButton
          onClose={() => setClosedAlertDismissed(true)}
        >
          {closedExchanges.map((e) => (
            <Text key={e.exchange} size="sm">
              <Text span fw={600}>{e.exchange}</Text> — chiusa per {e.reason}
            </Text>
          ))}
          <Text size="xs" c="dimmed" mt={4}>
            I prezzi mostrati potrebbero riferirsi all&apos;ultima chiusura disponibile.
          </Text>
        </Alert>
      )}

      <Text size="xs" c="dimmed">
        Ultimo aggiornamento: {lastUpdatedAt ? formatDateTime(lastUpdatedAt) : 'N/D'}
      </Text>

      {degradedItems.length > 0 && (
        <Alert color="yellow" variant="light" title="Alcune quotazioni non sono realtime">
          <Text size="sm">
            {degradedItems.length === 1
              ? '1 strumento usa un prezzo differito o di fallback.'
              : `${degradedItems.length} strumenti usano prezzi differiti o di fallback.`}
          </Text>
          <Text size="xs" c="dimmed" mt={4}>
            {degradedItems
              .slice(0, 4)
              .map((item) => `${item.symbol}${item.price_source ? ` (${formatPriceSourceLabel(item.price_source)})` : ''}`)
              .join(' • ')}
          </Text>
        </Alert>
      )}

      {error && <Alert color="red">{error instanceof Error ? error.message : 'Errore caricamento mercati'}</Alert>}

      {!isLoading && !data && !error && (
        <Text size="sm" c="dimmed">Nessun dato di mercato disponibile.</Text>
      )}

      {data?.categories.map((category) => (
        <Card key={category.category} withBorder radius="md" p="sm" shadow="sm">
          <Text fw={700} mb="sm">{category.label}</Text>
          <SimpleGrid cols={{ base: 1, xs: 2, sm: 2, md: 3, lg: 4 }} spacing="sm">
            {category.items.map((item) => (
              <MarketItemCard key={item.symbol} item={item} onClick={() => setSelectedSymbol(item.symbol)} />
            ))}
          </SimpleGrid>
        </Card>
      ))}

      {selectedSymbol && (
        <AssetInfoModal
          symbol={selectedSymbol}
          opened={!!selectedSymbol}
          onClose={() => setSelectedSymbol(null)}
        />
      )}
    </Stack>
  );
}
