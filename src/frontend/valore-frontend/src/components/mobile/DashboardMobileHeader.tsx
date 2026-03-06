import { Badge, Box, Group, Loader, Stack, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { PortfolioSwitcher } from '../portfolio/PortfolioSwitcher';
import { formatDateTime } from '../dashboard/formatters';
import type { Portfolio } from '../../services/api';

interface DashboardMobileHeaderProps {
  portfolios: Portfolio[];
  selectedPortfolioId: string | null;
  onSelectPortfolio: (value: string) => void;
  portfoliosLoading: boolean;
  refreshMessage: string | null;
  lastUpdatedAt: string | null;
}

export function DashboardMobileHeader({
  portfolios,
  selectedPortfolioId,
  onSelectPortfolio,
  portfoliosLoading,
  refreshMessage,
  lastUpdatedAt,
}: DashboardMobileHeaderProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <Box
      style={{
        marginBottom: 10,
        paddingTop: 2,
      }}
    >
      <Box
        style={{
          borderRadius: 24,
          padding: 10,
          background: isDark
            ? `linear-gradient(180deg, ${theme.colors.dark[7]}F5 0%, ${theme.colors.dark[6]}EB 100%)`
            : 'linear-gradient(180deg, rgba(248,250,252,0.96) 0%, rgba(255,255,255,0.92) 100%)',
          backdropFilter: 'blur(14px)',
          border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(148,163,184,0.18)',
          boxShadow: isDark ? '0 16px 42px rgba(0, 0, 0, 0.28)' : '0 16px 42px rgba(15, 23, 42, 0.10)',
        }}
      >
        <Stack gap={8}>
          <PortfolioSwitcher
            portfolios={portfolios}
            value={selectedPortfolioId}
            onChange={onSelectPortfolio}
            loading={portfoliosLoading}
          />

          <Group gap="xs" wrap="wrap">
            {refreshMessage ? (
              <Badge variant="light" color="teal">
                {refreshMessage}
              </Badge>
            ) : lastUpdatedAt ? (
              <Badge variant="light" color="green" leftSection={<IconSparkles size={12} />}>
                {`Aggiornato ${formatDateTime(lastUpdatedAt)}`}
              </Badge>
            ) : null}
            {portfoliosLoading && (
              <Badge variant="light" color="gray" leftSection={<Loader size={12} />}>
                Caricamento portafogli...
              </Badge>
            )}
          </Group>
        </Stack>
      </Box>
    </Box>
  );
}
