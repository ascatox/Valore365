import type { CSSProperties, ReactNode } from 'react';
import { Box, useComputedColorScheme, useMantineTheme } from '@mantine/core';

type PageLayoutVariant = 'default' | 'editorial' | 'fire' | 'settings';

interface PageLayoutProps {
  children: ReactNode;
  variant?: PageLayoutVariant;
  mobileBottomPadding?: number | string;
  style?: CSSProperties;
}

export function PageLayout({
  children,
  variant = 'default',
  mobileBottomPadding,
  style,
}: PageLayoutProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const background = variant === 'editorial'
    ? (isDark
      ? `radial-gradient(circle at top left, rgba(32, 201, 151, 0.14), transparent 24%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 28%, ${theme.colors.dark[8]} 100%)`
      : 'radial-gradient(circle at top left, rgba(19,78,74,0.10), transparent 24%), linear-gradient(180deg, #f7fbfa 0%, #ffffff 26%, #fffaf1 100%)')
    : variant === 'fire'
      ? (isDark
        ? `radial-gradient(circle at top left, rgba(250, 82, 82, 0.16), transparent 24%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 24%, ${theme.colors.dark[8]} 100%)`
        : 'radial-gradient(circle at top left, rgba(201,42,42,0.10), transparent 24%), linear-gradient(180deg, #fff5f5 0%, #ffffff 26%, #fff0f0 100%)')
    : variant === 'settings'
      ? (isDark
        ? `radial-gradient(circle at top left, rgba(148, 163, 184, 0.12), transparent 24%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 24%, ${theme.colors.dark[8]} 100%)`
        : 'radial-gradient(circle at top left, rgba(148,163,184,0.12), transparent 24%), linear-gradient(180deg, #f1f5f9 0%, #ffffff 26%, #f8fafc 100%)')
    : (isDark
      ? `radial-gradient(circle at top left, rgba(51, 154, 240, 0.08), transparent 22%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 24%, ${theme.colors.dark[8]} 100%)`
      : 'radial-gradient(circle at top left, rgba(15, 23, 42, 0.04), transparent 24%), linear-gradient(180deg, #f8fafc 0%, #ffffff 24%, #f8fafc 100%)');

  return (
    <Box
      style={{
        minHeight: '100%',
        padding: 'var(--mantine-spacing-sm)',
        paddingBottom: mobileBottomPadding,
        background,
        ...style,
      }}
    >
      {children}
    </Box>
  );
}
