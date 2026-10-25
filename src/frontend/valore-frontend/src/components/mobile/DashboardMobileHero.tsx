import { Badge, Box, Group, Loader, Stack, Text } from '@mantine/core';
import { IconArrowDownRight, IconArrowUpRight } from '@tabler/icons-react';
import type { PortfolioSummary } from '../../services/api';
import { formatMoney, formatPct, getVariationColor } from '../dashboard/formatters';

interface DashboardMobileHeroProps {
  summary: PortfolioSummary | null | undefined;
  statusText?: string | null;
  refreshing?: boolean;
}

// First thing on the mobile home: total wealth, today's move and total P/L.
export function DashboardMobileHero({ summary, statusText, refreshing = false }: DashboardMobileHeroProps) {
  const currency = summary?.base_currency ?? 'EUR';
  const total = summary ? summary.market_value + summary.cash_balance : null;
  const dayColor = getVariationColor(summary?.day_change ?? 0);
  const DayIcon = (summary?.day_change ?? 0) < 0 ? IconArrowDownRight : IconArrowUpRight;

  return (
    <Stack gap={6} py={4}>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: 0.8 }}>
        Patrimonio totale
      </Text>
      <Text fw={800} lh={1.05} style={{ fontSize: 34, letterSpacing: '-0.02em' }}>
        {total != null ? formatMoney(total, currency) : '—'}
      </Text>
      {summary && (
        <Group gap={8} wrap="wrap">
          <Badge
            variant="light"
            color={dayColor}
            size="lg"
            radius="xl"
            leftSection={<DayIcon size={14} />}
            styles={{ root: { textTransform: 'none', fontSize: 13 } }}
          >
            {`${formatMoney(summary.day_change, currency, true)} · ${formatPct(summary.day_change_pct)}`}
          </Badge>
          <Text size="sm" c="dimmed">oggi</Text>
        </Group>
      )}
      {summary && (
        <Text size="sm" c="dimmed">
          {'P/L totale '}
          <Text span fw={700} c={getVariationColor(summary.unrealized_pl)}>
            {formatMoney(summary.unrealized_pl, currency, true)}
          </Text>
          {` · ${formatPct(summary.unrealized_pl_pct)}`}
        </Text>
      )}
      {statusText && (
        <Box>
          <Group gap={6} wrap="nowrap">
            {refreshing && <Loader size={10} />}
            <Text size="xs" c="dimmed">{statusText}</Text>
          </Group>
        </Box>
      )}
    </Stack>
  );
}
