import { Box, Group, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconTrendingDown, IconTrendingUp } from '@tabler/icons-react';
import { useMarketQuotes } from '../hooks/queries';
import type { MarketQuoteItem } from '../../../services/api';

const ANIMATION_DURATION_PER_ITEM = 3; // seconds per item

function formatTickerPrice(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const abs = Math.abs(value);
  const decimals = abs >= 1000 ? 2 : abs >= 1 ? 2 : 4;
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
}

function formatTickerChange(pct: number | null): string {
  if (pct == null || !Number.isFinite(pct)) return '';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function TickerItem({ item, isDark }: { item: MarketQuoteItem; isDark: boolean }) {
  const theme = useMantineTheme();
  const pct = item.change_pct;
  const isPositive = pct != null && pct >= 0;
  const color = pct == null ? (isDark ? theme.colors.dark[1] : '#666')
    : isPositive ? '#16a34a' : '#dc2626';

  return (
    <Group
      gap={8}
      wrap="nowrap"
      style={{
        padding: '0 20px',
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      <Text fw={700} size="sm" style={{ whiteSpace: 'nowrap' }}>
        {item.name}
      </Text>
      <Text fw={600} size="sm" style={{ whiteSpace: 'nowrap' }}>
        {formatTickerPrice(item.price)}
      </Text>
      {pct != null && (
        <Group gap={2} wrap="nowrap">
          {isPositive
            ? <IconTrendingUp size={14} color={color} />
            : <IconTrendingDown size={14} color={color} />}
          <Text fw={600} size="sm" c={color} style={{ whiteSpace: 'nowrap' }}>
            {formatTickerChange(pct)}
          </Text>
        </Group>
      )}
    </Group>
  );
}

export function MarketTicker() {
  const { data } = useMarketQuotes();
  const colorScheme = useComputedColorScheme('light');
  const theme = useMantineTheme();
  const isDark = colorScheme === 'dark';

  const allItems: MarketQuoteItem[] = data?.categories.flatMap((c) => c.items) ?? [];

  if (allItems.length === 0) return null;

  const duration = allItems.length * ANIMATION_DURATION_PER_ITEM;
  const bgColor = isDark ? theme.colors.dark[8] : '#f8f9fa';
  const borderColor = isDark ? theme.colors.dark[5] : '#e9ecef';

  return (
    <Box
      style={{
        overflow: 'hidden',
        position: 'relative',
        borderRadius: 8,
        background: bgColor,
        border: `1px solid ${borderColor}`,
      }}
    >
      {/* Fade edges */}
      <Box
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          width: 40,
          zIndex: 1,
          background: `linear-gradient(to right, ${bgColor}, transparent)`,
          pointerEvents: 'none',
        }}
      />
      <Box
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          width: 40,
          zIndex: 1,
          background: `linear-gradient(to left, ${bgColor}, transparent)`,
          pointerEvents: 'none',
        }}
      />

      <Box
        style={{
          display: 'flex',
          alignItems: 'center',
          width: 'max-content',
          animation: `ticker-scroll ${duration}s linear infinite`,
          padding: '8px 0',
        }}
      >
        {/* Render items twice for seamless loop */}
        {allItems.map((item) => (
          <TickerItem key={`a-${item.symbol}`} item={item} isDark={isDark} />
        ))}
        {allItems.map((item) => (
          <TickerItem key={`b-${item.symbol}`} item={item} isDark={isDark} />
        ))}
      </Box>

      <style>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="ticker-scroll"] {
            animation: none !important;
          }
        }
      `}</style>
    </Box>
  );
}
