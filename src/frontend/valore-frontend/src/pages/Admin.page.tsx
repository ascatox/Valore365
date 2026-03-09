import { useEffect, useState } from 'react';
import { Alert, Card, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconChartBar, IconLock } from '@tabler/icons-react';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { getAdminUsageSummary, type AdminUsageSummary } from '../services/api';

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <Card withBorder radius="xl" padding="lg" style={{ background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)' }}>
      <Text size="sm" c="dimmed" fw={600}>{label}</Text>
      <Title order={2} mt={6}>{value.toLocaleString('it-IT')}</Title>
    </Card>
  );
}

export function AdminPage() {
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
              <MetricCard label="Utenti registrati" value={summary.registered_users} />
              <MetricCard label="Utenti con portfolio" value={summary.users_with_portfolios} />
              <MetricCard label="Utenti con transazioni" value={summary.users_with_transactions} />
              <MetricCard label="Utenti con import" value={summary.users_with_imports} />
              <MetricCard label="Portfolio creati" value={summary.portfolios_total} />
              <MetricCard label="Transazioni totali" value={summary.transactions_total} />
              <MetricCard label="Import batch totali" value={summary.csv_import_batches_total} />
              <MetricCard label="Portfolio creati 7 giorni" value={summary.portfolios_created_7d} />
              <MetricCard label="Import avviati 7 giorni" value={summary.imports_started_7d} />
            </SimpleGrid>

            <Card withBorder radius="xl" padding="lg">
              <Stack gap="xs">
                <Text fw={700}><IconChartBar size={16} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />Lettura attuale</Text>
                <Text c="dimmed">
                  Questi numeri misurano l'uso autenticato dell'app: account che hanno creato portfolio, inserito transazioni o avviato import.
                </Text>
                <Text c={summary.public_instant_analyzer_tracked ? 'teal' : 'orange'}>
                  Public instant analyzer tracciato: {summary.public_instant_analyzer_tracked ? 'si' : 'no'}
                </Text>
              </Stack>
            </Card>
          </>
        )}
      </Stack>
    </PageLayout>
  );
}
