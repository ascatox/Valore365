import { useEffect, useState } from 'react';
import { Alert, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import {
  IconChartBar,
  IconLock,
  IconUsers,
  IconBriefcase,
  IconArrowsExchange,
  IconFileImport,
  IconCalendar,
  IconSparkles,
} from '@tabler/icons-react';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { getAdminUsageSummary, type AdminUsageSummary } from '../services/api';

const METRIC_ICONS: Record<string, { icon: typeof IconUsers; color: string }> = {
  registered_users: { icon: IconUsers, color: 'blue' },
  users_with_portfolios: { icon: IconBriefcase, color: 'teal' },
  users_with_transactions: { icon: IconArrowsExchange, color: 'indigo' },
  users_with_imports: { icon: IconFileImport, color: 'grape' },
  portfolios_total: { icon: IconBriefcase, color: 'cyan' },
  transactions_total: { icon: IconArrowsExchange, color: 'orange' },
  csv_import_batches_total: { icon: IconFileImport, color: 'pink' },
  portfolios_created_7d: { icon: IconCalendar, color: 'lime' },
  imports_started_7d: { icon: IconCalendar, color: 'yellow' },
};

function MetricCard({ label, value, metricKey }: { label: string; value: number; metricKey: string }) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const iconConfig = METRIC_ICONS[metricKey];
  const Icon = iconConfig?.icon ?? IconChartBar;
  const color = iconConfig?.color ?? 'blue';

  return (
    <Card
      withBorder
      radius="xl"
      padding="lg"
      style={{
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        borderColor: isDark ? theme.colors.dark[4] : undefined,
      }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4}>
          <Text size="sm" c="dimmed" fw={600}>{label}</Text>
          <Title order={2} c={isDark ? 'white' : undefined}>{value.toLocaleString('it-IT')}</Title>
        </Stack>
        <ThemeIcon color={color} variant="light" size="lg" radius="xl">
          <Icon size={18} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

export function AdminPage() {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const [summary, setSummary] = useState<AdminUsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getAdminUsageSummary()
      .then((response) => {
        if (active) {
          setSummary(response);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Impossibile caricare i dati admin');
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <PageLayout variant="settings">
      <Stack gap="lg">
        <PageHeader
          eyebrow="Area riservata"
          title="Admin"
          description="Panoramica sintetica di quanti utenti stanno realmente provando Valore365."
        />

        {error && (
          <Alert color="red" icon={<IconLock size={16} />}>
            {error}
          </Alert>
        )}

        {summary && (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              <MetricCard label="Utenti registrati" value={summary.registered_users} metricKey="registered_users" />
              <MetricCard label="Utenti con portfolio" value={summary.users_with_portfolios} metricKey="users_with_portfolios" />
              <MetricCard label="Utenti con transazioni" value={summary.users_with_transactions} metricKey="users_with_transactions" />
              <MetricCard label="Utenti con import" value={summary.users_with_imports} metricKey="users_with_imports" />
              <MetricCard label="Portfolio creati" value={summary.portfolios_total} metricKey="portfolios_total" />
              <MetricCard label="Transazioni totali" value={summary.transactions_total} metricKey="transactions_total" />
              <MetricCard label="Import batch totali" value={summary.csv_import_batches_total} metricKey="csv_import_batches_total" />
              <MetricCard label="Portfolio creati 7 giorni" value={summary.portfolios_created_7d} metricKey="portfolios_created_7d" />
              <MetricCard label="Import avviati 7 giorni" value={summary.imports_started_7d} metricKey="imports_started_7d" />
            </SimpleGrid>

            <Card
              withBorder
              radius="xl"
              padding="lg"
              style={{
                background: isDark
                  ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                  : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
                borderColor: isDark ? theme.colors.dark[4] : undefined,
              }}
            >
              <Stack gap="xs">
                <Group gap="xs">
                  <ThemeIcon color="blue" variant="light" size="sm" radius="xl">
                    <IconChartBar size={14} />
                  </ThemeIcon>
                  <Text fw={700} c={isDark ? 'white' : undefined}>Lettura attuale</Text>
                </Group>
                <Text c="dimmed">
                  Questi numeri misurano l'uso autenticato dell'app: account che hanno creato portfolio, inserito transazioni o avviato import.
                </Text>
                <Group gap="xs">
                  <ThemeIcon
                    color={summary.public_instant_analyzer_tracked ? 'teal' : 'orange'}
                    variant="light"
                    size="sm"
                    radius="xl"
                  >
                    <IconSparkles size={14} />
                  </ThemeIcon>
                  <Text c={summary.public_instant_analyzer_tracked ? 'teal' : 'orange'} fw={600}>
                    Public instant analyzer: {summary.public_instant_analyzer_tracked ? 'attivo' : 'non attivo'}
                  </Text>
                </Group>
              </Stack>
            </Card>
          </>
        )}
      </Stack>
    </PageLayout>
  );
}
