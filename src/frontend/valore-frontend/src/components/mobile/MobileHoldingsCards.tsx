import { Badge, Box, Card, Group, Progress, Stack, Text, Tooltip, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconAlertTriangle, IconArrowUpRight, IconTarget, IconTrendingUp, IconWallet } from '@tabler/icons-react';
import type { Position, PortfolioSummary } from '../../services/api';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../dashboard/formatters';

interface MobileHoldingsCardsProps {
  positions: Position[];
  currency: string;
  summary?: PortfolioSummary | null;
  targetMap?: Map<number, number>;
}

function formatFirstTrade(value?: string | null): string {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatPriceDate(value?: string | null): string {
  if (!value) return 'N/D';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return 'N/D';
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

export function MobileHoldingsCards({ positions, currency, summary, targetMap }: MobileHoldingsCardsProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const hasTargets = targetMap && targetMap.size > 0;

  const totals = (() => {
    const totalValue = summary?.market_value ?? positions.reduce((sum, position) => sum + position.market_value, 0);
    const totalPl = summary?.unrealized_pl ?? positions.reduce((sum, position) => sum + position.unrealized_pl, 0);
    const totalCost = summary?.cost_basis ?? positions.reduce((sum, position) => sum + (position.market_value - position.unrealized_pl), 0);
    const totalPlPct = summary?.unrealized_pl_pct ?? (totalCost > 0 ? (totalPl / totalCost) * 100 : 0);
    return { totalValue, totalPl, totalPlPct };
  })();

  if (!positions.length) {
    return (
      <Card withBorder radius="xl" p="lg" bg={isDark ? theme.colors.dark[6] : '#f8fafc'}>
        <Text c="dimmed" ta="center" size="sm">Nessuna posizione disponibile</Text>
      </Card>
    );
  }

  return (
    <Stack gap="md">
      {positions.map((position) => {
        const target = targetMap?.get(position.asset_id);
        const delta = target != null ? position.weight - target : null;
        const warnTarget = delta != null && Math.abs(delta) > 5;
        const plColor = getVariationColor(position.unrealized_pl);
        const pctColor = getVariationColor(position.unrealized_pl_pct);
        const dayColor = getVariationColor(position.day_change_pct);

        return (
          <Card
            key={position.asset_id}
            withBorder
            radius="xl"
            p="lg"
            style={{
              background: isDark
                ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              boxShadow: isDark ? '0 18px 36px rgba(0, 0, 0, 0.28)' : '0 18px 36px rgba(15, 23, 42, 0.08)',
            }}
          >
            <Stack gap="md">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Box style={{ minWidth: 0 }}>
                  <Group gap={6} wrap="wrap" mb={6}>
                    <Text fw={800} size="lg" c={isDark ? theme.white : '#0f172a'}>{position.symbol}</Text>
                    {position.price_stale && (
                      <Tooltip
                        label={`Prezzo non aggiornato${position.price_date ? ` (ultimo: ${formatPriceDate(position.price_date)})` : ''}`}
                        withArrow
                      >
                        <Badge color="yellow" variant="light" leftSection={<IconAlertTriangle size={12} />}>
                          Prezzo stale
                        </Badge>
                      </Tooltip>
                    )}
                  </Group>
                  <Text size="sm" c="dimmed" lineClamp={2}>{position.name}</Text>
                </Box>

                <Box
                  style={{
                    minWidth: 112,
                    borderRadius: 18,
                    padding: '10px 12px',
                    background: isDark ? 'rgba(20, 184, 166, 0.12)' : 'linear-gradient(135deg, rgba(15,118,110,0.10), rgba(15,118,110,0.04))',
                    border: isDark ? `1px solid ${theme.colors.teal[8]}` : '1px solid rgba(15,118,110,0.12)',
                    textAlign: 'right',
                  }}
                >
                  <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.teal[3] : '#0f766e'} style={{ letterSpacing: 0.8 }}>
                    Valore
                  </Text>
                  <Text fw={800} size="sm" c={isDark ? theme.white : '#0f172a'}>{formatMoney(position.market_value, currency)}</Text>
                </Box>
              </Group>

              <Group grow>
                <Box
                  style={{
                    borderRadius: 18,
                    padding: '12px 14px',
                    background: isDark ? theme.colors.dark[5] : '#f8fafc',
                    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
                  }}
                >
                  <Group justify="space-between" wrap="nowrap" mb={4}>
                    <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} style={{ letterSpacing: 0.8 }}>
                      P/L
                    </Text>
                    <IconArrowUpRight size={14} color={plColor === 'green' ? '#16a34a' : plColor === 'red' ? '#dc2626' : (isDark ? theme.colors.gray[4] : '#64748b')} />
                  </Group>
                  <Text fw={800} size="sm" c={plColor}>{formatMoney(position.unrealized_pl, currency, true)}</Text>
                  <Text size="xs" c={pctColor}>{formatPct(position.unrealized_pl_pct)}</Text>
                </Box>

                <Box
                  style={{
                    borderRadius: 18,
                    padding: '12px 14px',
                    background: isDark ? theme.colors.dark[5] : '#f8fafc',
                    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
                  }}
                >
                  <Group justify="space-between" wrap="nowrap" mb={4}>
                    <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} style={{ letterSpacing: 0.8 }}>
                      Oggi
                    </Text>
                    <IconTrendingUp size={14} color={dayColor === 'green' ? '#16a34a' : dayColor === 'red' ? '#dc2626' : (isDark ? theme.colors.gray[4] : '#64748b')} />
                  </Group>
                  <Text fw={800} size="sm" c={dayColor}>{formatPct(position.day_change_pct)}</Text>
                </Box>

                <Box
                  style={{
                    borderRadius: 18,
                    padding: '12px 14px',
                    background: isDark ? theme.colors.dark[5] : '#f8fafc',
                    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
                  }}
                >
                  <Group justify="space-between" wrap="nowrap" mb={4}>
                    <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} style={{ letterSpacing: 0.8 }}>
                      Peso
                    </Text>
                    <IconWallet size={14} color={theme.colors.blue[5]} />
                  </Group>
                  <Progress value={position.weight} size="sm" radius="xl" color="blue" mb={6} />
                  <Text fw={700} size="sm">{formatNum(position.weight, 1)}%</Text>
                </Box>
              </Group>

              <Group gap="xs" wrap="wrap">
                <Badge variant="light" color="gray">{`Qta ${formatNum(position.quantity)}`}</Badge>
                <Badge variant="light" color="gray">{`Prezzo ${formatMoney(position.market_price, currency)}`}</Badge>
                <Badge variant="light" color="gray">{`Prima op. ${formatFirstTrade(position.first_trade_at)}`}</Badge>
                {hasTargets && target != null && (
                  <Badge
                    variant="light"
                    color={warnTarget ? 'orange' : 'teal'}
                    leftSection={<IconTarget size={12} />}
                  >
                    {`Target ${formatNum(target, 1)}%${delta != null ? ` · ${delta > 0 ? '+' : ''}${formatNum(delta, 1)}%` : ''}`}
                  </Badge>
                )}
              </Group>
            </Stack>
          </Card>
        );
      })}

      <Card
        radius="xl"
        p="lg"
        style={{
          background: isDark
            ? `linear-gradient(135deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[6]} 100%)`
            : 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          color: '#ffffff',
          boxShadow: isDark ? '0 18px 36px rgba(0, 0, 0, 0.34)' : '0 18px 36px rgba(15, 23, 42, 0.20)',
        }}
      >
        <Stack gap="sm">
          <Group justify="space-between" wrap="nowrap">
            <Text fw={700} size="sm" c="rgba(255,255,255,0.72)">Totale portafoglio</Text>
            <Text fw={800} size="lg">{formatMoney(totals.totalValue, currency)}</Text>
          </Group>
          <Group grow>
            <Box>
              <Text size="xs" fw={700} tt="uppercase" c="rgba(255,255,255,0.58)" style={{ letterSpacing: 0.8 }}>
                P/L
              </Text>
              <Text fw={800} size="sm" c={totals.totalPl > 0 ? '#86efac' : totals.totalPl < 0 ? '#fca5a5' : '#e2e8f0'}>
                {formatMoney(totals.totalPl, currency, true)}
              </Text>
            </Box>
            <Box>
              <Text size="xs" fw={700} tt="uppercase" c="rgba(255,255,255,0.58)" style={{ letterSpacing: 0.8 }}>
                P/L %
              </Text>
              <Text fw={800} size="sm" c={totals.totalPlPct > 0 ? '#86efac' : totals.totalPlPct < 0 ? '#fca5a5' : '#e2e8f0'}>
                {formatPct(totals.totalPlPct)}
              </Text>
            </Box>
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}
