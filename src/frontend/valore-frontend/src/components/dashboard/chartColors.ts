import { useComputedColorScheme, useMantineTheme } from '@mantine/core';

/**
 * Chart colours from the theme, so series follow the brand palette and stay
 * readable in both colour schemes:
 * - primary: the main series (portfolio value, TWR, CAGR)
 * - gain / loss: values whose sign is the message (P/L, daily moves, drawdown)
 * - attention: risk measures (volatility)
 * - secondary: a second, non-semantic series (Sharpe)
 * - benchmark: comparison series, deliberately quiet
 */
export function useChartColors() {
  const theme = useMantineTheme();
  const isDark = useComputedColorScheme('light') === 'dark';
  const shade = isDark ? 4 : 6;

  return {
    primary: theme.colors.teal[shade],
    gain: theme.colors.green[shade],
    loss: theme.colors.red[shade],
    attention: theme.colors.orange[shade],
    secondary: isDark ? '#8aa4c0' : '#47607a',
    benchmark: isDark ? theme.colors.gray[5] : theme.colors.gray[6],
    signed: (value: number | null | undefined) => ((value ?? 0) < 0 ? theme.colors.red[shade] : theme.colors.green[shade]),
  };
}
