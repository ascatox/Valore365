import { useState } from 'react';
import { Card, Group, Loader, Paper, Text, UnstyledButton } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer } from 'recharts';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';

interface GainTwrChartProps {
  data: Array<{ date: string; gain?: number; twr?: number }>;
  loading: boolean;
  currency: string;
  lastGain: number | null;
  lastTwr: number | null;
}

export function GainTwrChart({ data, loading, currency, lastGain, lastTwr }: GainTwrChartProps) {
  const [showGain, setShowGain] = useState(true);
  const [showTwr, setShowTwr] = useState(true);

  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const gainChartColor = lastGain != null && lastGain >= 0 ? '#16a34a' : '#dc2626';
  const twrChartColor = lastTwr != null && lastTwr >= 0 ? '#2563eb' : '#9333ea';

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text fw={600} size="sm">Guadagno & TWR</Text>
          {lastGain != null && (
            <UnstyledButton onClick={() => setShowGain((value) => !value)}>
              <Text
                size="xs"
                fw={600}
                c={showGain ? getVariationColor(lastGain) : 'dimmed'}
                td={showGain ? undefined : 'line-through'}
                style={{ cursor: 'pointer' }}
              >
                Guadagno: {formatMoney(lastGain, currency, true)}
              </Text>
            </UnstyledButton>
          )}
          {lastTwr != null && (
            <UnstyledButton onClick={() => setShowTwr((value) => !value)}>
              <Text
                size="xs"
                fw={600}
                c={showTwr ? getVariationColor(lastTwr) : 'dimmed'}
                td={showTwr ? undefined : 'line-through'}
                style={{ cursor: 'pointer' }}
              >
                TWR: {formatPct(lastTwr)}
              </Text>
            </UnstyledButton>
          )}
        </Group>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">Guadagno assoluto e rendimento TWR combinati.</Text>
      <div style={{ height: 260 }}>
        {loading ? (
          <Group h="100%" justify="center">
            <Loader size="sm" />
            <Text c="dimmed" size="sm">Caricamento...</Text>
          </Group>
        ) : data.length === 0 ? (
          <Group h="100%" justify="center">
            <Text c="dimmed" size="sm">Nessun dato disponibile</Text>
          </Group>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="dualGainGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={gainChartColor} stopOpacity={0.18} />
                  <stop offset="95%" stopColor={gainChartColor} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="dualTwrGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={twrChartColor} stopOpacity={0.18} />
                  <stop offset="95%" stopColor={twrChartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
              <YAxis
                yAxisId="gain"
                orientation="left"
                axisLine={false}
                tickLine={false}
                tick={{ fill: tickColor, fontSize: 11 }}
                width={55}
                tickFormatter={(value: number) => formatNum(value, value >= 1000 ? 0 : 1)}
                hide={!showGain}
              />
              <YAxis
                yAxisId="twr"
                orientation="right"
                axisLine={false}
                tickLine={false}
                tick={{ fill: tickColor, fontSize: 11 }}
                width={45}
                tickFormatter={(value: number) => `${formatNum(value, 1)}%`}
                hide={!showTwr}
              />
              <RTooltip
                content={({ active, payload, label }: any) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <Paper withBorder p="xs" radius="sm" shadow="xs">
                      <Text size="xs" c="dimmed">{label}</Text>
                      {payload.map((entry: any) => {
                        const value = Number(entry.value ?? 0);
                        if (!Number.isFinite(value)) return null;
                        const isGain = entry.dataKey === 'gain';
                        return (
                          <Text key={entry.dataKey} size="sm" fw={600} c={getVariationColor(value)}>
                            {isGain ? `Guadagno: ${formatMoney(value, currency, true)}` : `TWR: ${formatPct(value)}`}
                          </Text>
                        );
                      })}
                    </Paper>
                  );
                }}
              />
              {showGain && (
                <Area
                  yAxisId="gain"
                  type="monotone"
                  dataKey="gain"
                  stroke={gainChartColor}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#dualGainGrad)"
                  name="Guadagno"
                />
              )}
              {showTwr && (
                <Area
                  yAxisId="twr"
                  type="monotone"
                  dataKey="twr"
                  stroke={twrChartColor}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#dualTwrGrad)"
                  name="TWR %"
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
