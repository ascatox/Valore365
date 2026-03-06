import { ActionIcon, Badge, Box, Group, Loader, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconArrowsExchange, IconRefresh, IconSparkles } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { PortfolioSwitcher } from '../portfolio/PortfolioSwitcher';
import { formatDateTime } from '../dashboard/formatters';
import type { Portfolio } from '../../services/api';

interface DashboardMobileHeaderProps {
  portfolios: Portfolio[];
  selectedPortfolioId: string | null;
  onSelectPortfolio: (value: string) => void;
  portfoliosLoading: boolean;
  refreshing: boolean;
  refreshMessage: string | null;
  lastUpdatedAt: string | null;
  onRefresh: () => void;
}

export function DashboardMobileHeader({
  portfolios,
  selectedPortfolioId,
  onSelectPortfolio,
  portfoliosLoading,
  refreshing,
  refreshMessage,
  lastUpdatedAt,
  onRefresh,
}: DashboardMobileHeaderProps) {
  const navigate = useNavigate();

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
                Dashboard mobile
              </Text>
              <Text fw={800} size="xl" c="#0f172a">
                Valore365
              </Text>
              <Text size="sm" c="dimmed">
                Contesto, KPI e azioni sempre a portata di pollice
              </Text>
            </Box>
            <ActionIcon
              variant="light"
              color="teal"
              radius="xl"
              size={42}
              onClick={onRefresh}
              loading={refreshing}
              aria-label="Aggiorna dashboard"
            >
              <IconRefresh size={19} />
            </ActionIcon>
          </Group>

          <PortfolioSwitcher
            portfolios={portfolios}
            value={selectedPortfolioId}
            onChange={onSelectPortfolio}
            loading={portfoliosLoading}
            onOpenPortfolio={() => navigate('/portfolio')}
          />

          <Group grow>
            <UnstyledButton
              onClick={onRefresh}
              style={{
                borderRadius: 18,
                padding: '14px 16px',
                background: 'linear-gradient(135deg, #0f766e 0%, #134e4a 100%)',
                color: '#ffffff',
                boxShadow: '0 14px 30px rgba(15, 118, 110, 0.24)',
              }}
            >
              <Group justify="space-between" wrap="nowrap">
                <Box>
                  <Text size="xs" fw={700} tt="uppercase" style={{ letterSpacing: 0.8, opacity: 0.82 }}>
                    Dati
                  </Text>
                  <Text fw={700}>Aggiorna prezzi</Text>
                </Box>
                {refreshing ? <Loader size={16} color="#ffffff" /> : <IconRefresh size={18} />}
              </Group>
            </UnstyledButton>

            <UnstyledButton
              onClick={() => navigate('/portfolio')}
              style={{
                borderRadius: 18,
                padding: '14px 16px',
                background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
                color: '#0f172a',
                border: '1px solid #d6d9de',
                boxShadow: '0 12px 28px rgba(15, 23, 42, 0.08)',
              }}
            >
              <Group justify="space-between" wrap="nowrap">
                <Box>
                  <Text size="xs" fw={700} tt="uppercase" c="#64748b" style={{ letterSpacing: 0.8 }}>
                    Operativita'
                  </Text>
                  <Text fw={700}>Nuova transazione</Text>
                </Box>
                <IconArrowsExchange size={18} />
              </Group>
            </UnstyledButton>
          </Group>

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
