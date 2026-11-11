import { useEffect, useState } from 'react';
import { Alert, Badge, Card, Group, Loader, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
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
  IconUsersGroup,
  IconShieldCheck,
} from '@tabler/icons-react';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { getAdminUsageSummary, type AdminUsageSummary } from '../services/api';
import {
  AUDITOR_AREA_LABELS,
  getAuditorAdminLatest,
  type AuditorAdminLatest,
  type AuditorRunStatus,
  type AuditorSeverity,
} from '../services/api/auditor';

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
  analyzer_runs_total: { icon: IconSparkles, color: 'blue' },
  analyzer_runs_7d: { icon: IconSparkles, color: 'teal' },
  analyzer_unique_visitors_7d: { icon: IconUsersGroup, color: 'green' },
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
          <Title order={2} c={isDark ? 'white' : undefined}>{value.toLocaleString('it-IT', { useGrouping: 'always' })}</Title>
        </Stack>
        <ThemeIcon color={color} variant="light" size="lg" radius="xl">
          <Icon size={18} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

// --- Auditor dei calcoli (TASK-81): ultima corsa notturna --------------------------------------

const RUN_STATUS: Record<AuditorRunStatus, { label: string; color: string }> = {
  running: { label: 'In corso', color: 'blue' },
  success: { label: 'Tutto in ordine', color: 'teal' },
  completed_with_failures: { label: 'Conclusa con regole che falliscono', color: 'orange' },
  failed: { label: 'Corsa fallita', color: 'red' },
  interrupted: { label: 'Interrotta', color: 'gray' },
};

const SEVERITY_COLOR: Record<AuditorSeverity, string> = { P0: 'red', P1: 'orange', P2: 'yellow' };

function formatAdminDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const portfoliosLabel = (count: number) => (count === 1 ? '1 portafoglio' : `${count.toLocaleString('it-IT')} portafogli`);
const involvedLabel = (count: number) => (count === 1 ? '1 portafoglio coinvolto' : `${count.toLocaleString('it-IT')} portafogli coinvolti`);

/** Ultima corsa notturna: regole che falliscono, quanti portafogli, da quando, severità. Solo conteggi. */
export function AuditorAdminPanel({ data, error, loading }: { data: AuditorAdminLatest | null; error: string | null; loading: boolean }) {
  const run = data?.run ?? null;
  const status = run ? RUN_STATUS[run.status] ?? { label: run.status, color: 'gray' } : null;
  const failing = data?.failing ?? [];
  const errors = data?.errors ?? [];

  return (
    <Card withBorder radius="xl" padding="lg" data-testid="admin-auditor">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" gap="xs">
          <Group gap="xs" wrap="nowrap">
            <ThemeIcon color="teal" variant="light" size="sm" radius="xl">
              <IconShieldCheck size={14} />
            </ThemeIcon>
            <Text fw={700}>Controlli notturni dei calcoli</Text>
          </Group>
          {status && <Badge color={status.color} variant="light" data-testid="admin-auditor-status">{status.label}</Badge>}
        </Group>

        {loading && <Group gap="sm"><Loader size="sm" /><Text size="sm" c="dimmed">Caricamento dell'ultima corsa…</Text></Group>}
        {error && <Alert color="red" variant="light">{error}</Alert>}
        {!loading && !error && !run && (
          <Text size="sm" c="dimmed" data-testid="admin-auditor-empty">Nessuna corsa notturna registrata.</Text>
        )}

        {run && (
          <>
            <Text size="sm" c="dimmed">
              {`Avviata ${formatAdminDateTime(run.started_at)} · conclusa ${formatAdminDateTime(run.finished_at)} · `
                + `${run.rules_total} regole su ${portfoliosLabel(run.portfolios_total)}`}
            </Text>
            <Group gap="xs">
              <Badge color="teal" variant="light">{run.counts.pass === 1 ? '1 superato' : `${run.counts.pass} superati`}</Badge>
              <Badge color={run.counts.fail ? 'orange' : 'gray'} variant="light">{run.counts.fail === 1 ? '1 fallito' : `${run.counts.fail} falliti`}</Badge>
              <Badge color={run.counts.error ? 'red' : 'gray'} variant="light">{run.counts.error === 1 ? '1 errore' : `${run.counts.error} errori`}</Badge>
              <Badge color="gray" variant="light">{run.counts.skip === 1 ? '1 non applicabile' : `${run.counts.skip} non applicabili`}</Badge>
            </Group>
            {run.error_type && <Text size="sm" c="red">{`Eccezione: ${run.error_type}`}</Text>}

            {failing.length === 0 ? (
              <Text size="sm" data-testid="admin-auditor-none-failing">Nessuna regola fallisce nell'ultima corsa.</Text>
            ) : (
              <Stack gap="xs" data-testid="admin-auditor-failing">
                <Text size="sm" fw={600}>{failing.length === 1 ? '1 regola fallisce' : `${failing.length} regole falliscono`}</Text>
                {failing.map((rule) => (
                  <Paper key={rule.rule_id} withBorder radius="md" p="sm" data-testid="admin-auditor-rule">
                    <Group justify="space-between" align="flex-start" gap="xs" wrap="nowrap">
                      <Stack gap={2} style={{ minWidth: 0 }}>
                        <Text size="sm" fw={600} style={{ overflowWrap: 'anywhere' }}>{rule.title}</Text>
                        <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
                          {`${rule.rule_id}${rule.area ? ` · ${AUDITOR_AREA_LABELS[rule.area] ?? rule.area}` : ''}`}
                        </Text>
                        <Text size="xs">
                          {`${involvedLabel(rule.portfolios_failing)} · dal ${formatAdminDateTime(rule.since)}`}
                        </Text>
                      </Stack>
                      <Badge color={SEVERITY_COLOR[rule.severity] ?? 'gray'} variant="filled" style={{ flexShrink: 0 }}>
                        {rule.severity}
                      </Badge>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}

            {errors.length > 0 && (
              <Stack gap={4} data-testid="admin-auditor-errors">
                <Text size="sm" fw={600}>Regole in errore</Text>
                {errors.map((item) => (
                  <Text key={item.rule_id} size="xs" c="dimmed">{`${item.rule_id} · ${portfoliosLabel(item.portfolios)}`}</Text>
                ))}
              </Stack>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}

function AuditorAdminSection() {
  const [data, setData] = useState<AuditorAdminLatest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getAuditorAdminLatest()
      .then((response) => {
        if (active) setData(response);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Impossibile caricare l'ultima corsa");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return <AuditorAdminPanel data={data} error={error} loading={loading} />;
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
    <PageLayout>
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
              <MetricCard label="Analyzer usi totali" value={summary.analyzer_runs_total} metricKey="analyzer_runs_total" />
              <MetricCard label="Analyzer usi 7 giorni" value={summary.analyzer_runs_7d} metricKey="analyzer_runs_7d" />
              <MetricCard label="Visitatori unici analyzer 7 giorni" value={summary.analyzer_unique_visitors_7d} metricKey="analyzer_unique_visitors_7d" />
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
                  Questi numeri combinano l'uso autenticato dell'app con il tracking del public instant analyzer.
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

        {summary && <AuditorAdminSection />}
      </Stack>
    </PageLayout>
  );
}
