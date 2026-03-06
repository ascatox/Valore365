import { Badge, Box, Group, Loader, Stack, Text } from '@mantine/core';
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
  return (
    <Box
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 40,
        marginBottom: 16,
        paddingTop: 4,
      }}
    >
      <Box
        style={{
          borderRadius: 24,
          padding: 14,
          background: 'linear-gradient(180deg, rgba(248,250,252,0.96) 0%, rgba(255,255,255,0.92) 100%)',
          backdropFilter: 'blur(14px)',
          border: '1px solid rgba(148,163,184,0.18)',
          boxShadow: '0 16px 42px rgba(15, 23, 42, 0.10)',
        }}
      >
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box>
              <Text
                size="xs"
                fw={700}
                tt="uppercase"
                c="#0f766e"
                style={{ letterSpacing: 1 }}
              >
                Dashboard
              </Text>
            </Box>
          </Group>

          <PortfolioSwitcher
            portfolios={portfolios}
            value={selectedPortfolioId}
            onChange={onSelectPortfolio}
            loading={portfoliosLoading}
          />

          <Group gap="xs" wrap="wrap">
            {refreshMessage ? (
              <Badge variant="light" color="teal" size="lg">
                {refreshMessage}
              </Badge>
            ) : lastUpdatedAt ? (
              <Badge variant="light" color="green" size="lg" leftSection={<IconSparkles size={12} />}>
                {`Aggiornato ${formatDateTime(lastUpdatedAt)}`}
              </Badge>
            ) : null}
            {portfoliosLoading && (
              <Badge variant="light" color="gray" size="lg" leftSection={<Loader size={12} />}>
                Caricamento portafogli...
              </Badge>
            )}
          </Group>
        </Stack>
      </Box>
    </Box>
  );
}
