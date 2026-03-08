import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconFlame, IconTarget, IconTrendingUp, IconWallet } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMediaQuery } from '@mantine/hooks';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { useMonteCarloProjection, usePortfolioSummary, usePortfolios, useUserSettings } from '../components/dashboard/hooks/queries';
import { updateUserSettings } from '../services/api';

function formatMoney(value: number | null | undefined, currency = 'EUR'): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(digits)}%`;
}

function solveYearsToTarget(target: number, current: number, annualContribution: number, annualReturnPct: number): number | null {
  if (!Number.isFinite(target) || !Number.isFinite(current) || target <= 0) return null;
  if (current >= target) return 0;
  if (!Number.isFinite(annualContribution) || annualContribution < 0) return null;

  const r = annualReturnPct / 100;
  if (r === 0) {
    if (annualContribution <= 0) return null;
    return Math.max(0, (target - current) / annualContribution);
  }

  const denominator = current * r + annualContribution;
  const numerator = target * r + annualContribution;
  if (denominator <= 0 || numerator <= denominator) {
    return annualContribution > 0 ? Math.max(0, Math.log(numerator / denominator) / Math.log(1 + r)) : null;
  }

  const years = Math.log(numerator / denominator) / Math.log(1 + r);
  return Number.isFinite(years) && years >= 0 ? years : null;
}

function solveRequiredContribution(target: number, current: number, years: number, annualReturnPct: number): number | null {
  if (!Number.isFinite(target) || !Number.isFinite(current) || !Number.isFinite(years) || years <= 0) return null;
  if (current >= target) return 0;

  const r = annualReturnPct / 100;
  if (r === 0) return Math.max(0, (target - current) / years);

  const growth = (1 + r) ** years;
  const annuityFactor = (growth - 1) / r;
  if (annuityFactor <= 0) return null;
  return Math.max(0, (target - current * growth) / annuityFactor);
}

function projectionToValue(indexValue: number, investedValue: number, cashBalance: number): number {
  return (indexValue / 100) * investedValue + cashBalance;
}

export function FirePage() {
  const queryClient = useQueryClient();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });

  const { data: portfolios = [], isLoading: portfoliosLoading } = usePortfolios();
  const { data: userSettings, isLoading: settingsLoading } = useUserSettings();
  const portfolioId = selectedPortfolioId ? Number(selectedPortfolioId) : null;
  const { data: summary, isLoading: summaryLoading, error: summaryError } = usePortfolioSummary(portfolioId);
  const { data: monteCarlo, isLoading: monteCarloLoading } = useMonteCarloProjection(portfolioId);

  const [annualExpenses, setAnnualExpenses] = useState<number | string>(0);
  const [annualContribution, setAnnualContribution] = useState<number | string>(0);
  const [safeWithdrawalRate, setSafeWithdrawalRate] = useState<number | string>(4);
  const [currentAge, setCurrentAge] = useState<number | string>('');
  const [targetAge, setTargetAge] = useState<number | string>('');
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!portfolios.length) return;
    setSelectedPortfolioId((previous) => {
      const exists = previous ? portfolios.some((portfolio) => String(portfolio.id) === previous) : false;
      return exists ? previous : String(portfolios[0].id);
    });
  }, [portfolios]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (selectedPortfolioId) {
      window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, selectedPortfolioId);
    }
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!userSettings) return;
    setAnnualExpenses(userSettings.fire_annual_expenses ?? 0);
    setAnnualContribution(userSettings.fire_annual_contribution ?? 0);
    setSafeWithdrawalRate(userSettings.fire_safe_withdrawal_rate ?? 4);
    setCurrentAge(userSettings.fire_current_age ?? '');
    setTargetAge(userSettings.fire_target_age ?? '');
  }, [userSettings]);

  const settingsMutation = useMutation({
    mutationFn: updateUserSettings,
    onSuccess: async () => {
      setSaveError(null);
      setSaveMessage('Impostazioni FIRE salvate');
      await queryClient.invalidateQueries({ queryKey: ['user-settings'] });
    },
    onError: (error) => {
      setSaveMessage(null);
      setSaveError(error instanceof Error ? error.message : 'Errore salvataggio impostazioni FIRE');
    },
  });

  const selectedPortfolio = useMemo(
    () => portfolios.find((portfolio) => String(portfolio.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const currency = summary?.base_currency ?? selectedPortfolio?.base_currency ?? 'EUR';
  const investedValue = summary?.market_value ?? 0;
  const cashBalance = summary?.cash_balance ?? selectedPortfolio?.cash_balance ?? 0;
  const totalNetWorth = investedValue + cashBalance;
  const expensesValue = typeof annualExpenses === 'number' ? annualExpenses : Number(annualExpenses || 0);
  const contributionValue = typeof annualContribution === 'number' ? annualContribution : Number(annualContribution || 0);
  const swrValue = typeof safeWithdrawalRate === 'number' ? safeWithdrawalRate : Number(safeWithdrawalRate || 0);
  const currentAgeValue = typeof currentAge === 'number' ? currentAge : Number(currentAge || 0);
  const targetAgeValue = typeof targetAge === 'number' ? targetAge : Number(targetAge || 0);
  const hasAgePlan = currentAgeValue > 0 && targetAgeValue > currentAgeValue;
  const fireNumber = expensesValue > 0 && swrValue > 0 ? expensesValue / (swrValue / 100) : null;
  const coveragePct = fireNumber && fireNumber > 0 ? (totalNetWorth / fireNumber) * 100 : null;
  const fireGap = fireNumber != null ? Math.max(0, fireNumber - totalNetWorth) : null;
  const expectedReturnPct = monteCarlo?.annualized_mean_return_pct ?? 5;
  const estimatedYearsToFire = fireNumber != null
    ? solveYearsToTarget(fireNumber, totalNetWorth, contributionValue, expectedReturnPct)
    : null;
  const estimatedFireAge = estimatedYearsToFire != null && currentAgeValue > 0 ? currentAgeValue + estimatedYearsToFire : null;
  const requiredContribution = hasAgePlan && fireNumber != null
    ? solveRequiredContribution(fireNumber, totalNetWorth, targetAgeValue - currentAgeValue, expectedReturnPct)
    : null;

  const horizonScenarios = useMemo(() => {
    if (!monteCarlo || fireNumber == null) return [];
    return monteCarlo.projections
      .filter((projection) => projection.year > 0)
      .map((projection) => {
        const p25Value = projectionToValue(projection.p25, investedValue, cashBalance);
        const p50Value = projectionToValue(projection.p50, investedValue, cashBalance);
        const p75Value = projectionToValue(projection.p75, investedValue, cashBalance);
        return {
          year: projection.year,
          p25Value,
          p50Value,
          p75Value,
          onTrack: p50Value >= fireNumber,
          stretch: p75Value >= fireNumber,
        };
      })
      .slice(0, 5);
  }, [cashBalance, fireNumber, investedValue, monteCarlo]);

  const handleSave = () => {
    setSaveMessage(null);
    setSaveError(null);
    settingsMutation.mutate({
      fire_annual_expenses: Math.max(0, expensesValue || 0),
      fire_annual_contribution: Math.max(0, contributionValue || 0),
      fire_safe_withdrawal_rate: Math.max(0.1, swrValue || 4),
      fire_current_age: currentAgeValue > 0 ? currentAgeValue : null,
      fire_target_age: targetAgeValue > 0 ? targetAgeValue : null,
    });
  };

  return (
    <PageLayout variant="fire">
      <Stack gap="lg">
        <PageHeader
          eyebrow="Indipendenza finanziaria e piano di decumulo"
          title="FIRE"
          description="Stimatore operativo per Financial Independence, con soglia FIRE, traiettoria attesa e scenari di raggiungimento."
          actions={(
            <PortfolioSwitcher
              portfolios={portfolios}
              value={selectedPortfolioId}
              onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
              loading={portfoliosLoading}
              style={{ width: '100%', maxWidth: 360 }}
            />
          )}
        />

        {(summaryError instanceof Error) && <Alert color="red">{summaryError.message}</Alert>}
        {saveMessage && <Alert color="teal">{saveMessage}</Alert>}
        {saveError && <Alert color="red">{saveError}</Alert>}

        <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
          <Card
            radius="xl"
            padding="xl"
            withBorder
            style={{ background: 'linear-gradient(140deg, #5f1111 0%, #8f1d1d 56%, #ff8f6b 160%)', color: 'white' }}
          >
            <Stack gap="lg">
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <div>
                  <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.72 }}>FIRE Target</Text>
                  <Title order={1} mt={6} c="white" style={{ fontSize: 'clamp(2.8rem, 7vw, 5rem)', lineHeight: 0.95 }}>
                    {fireNumber != null ? formatMoney(fireNumber, currency) : '—'}
                  </Title>
                  <Text c="rgba(255,255,255,0.82)" mt="sm" size="lg">
                    Patrimonio attuale {formatMoney(totalNetWorth, currency)}
                  </Text>
                </div>
                <Badge size="xl" radius="sm" color={coveragePct != null && coveragePct >= 100 ? 'teal' : 'red'} variant="filled">
                  {coveragePct != null ? `${Math.min(999, coveragePct).toFixed(0)}% coperto` : 'Configura il piano'}
                </Badge>
              </Group>

              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                <HeroMetric label="Spesa annua" value={expensesValue > 0 ? formatMoney(expensesValue, currency) : '—'} />
                <HeroMetric label="SWR" value={swrValue > 0 ? formatPct(swrValue, 2) : '—'} />
                <HeroMetric label="Gap" value={fireGap != null ? formatMoney(fireGap, currency) : '—'} />
                <HeroMetric label="ETA" value={estimatedYearsToFire != null ? `${Math.ceil(estimatedYearsToFire)} anni` : 'N/D'} />
              </SimpleGrid>

              <Stack gap={8}>
                <Group justify="space-between">
                  <Text size="sm" c="rgba(255,255,255,0.82)">Avanzamento verso la soglia FIRE</Text>
                  <Text size="sm" fw={700} c="white">{coveragePct != null ? `${Math.min(100, coveragePct).toFixed(1)}%` : 'N/D'}</Text>
                </Group>
                <Progress value={Math.max(0, Math.min(100, coveragePct ?? 0))} color="red" radius="xl" size="lg" />
              </Stack>
            </Stack>
          </Card>

          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="red" variant="light" radius="xl">
                  <IconTarget size={18} />
                </ThemeIcon>
                <Title order={4}>Ipotesi del piano</Title>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <NumberInput label="Spesa annua target" value={annualExpenses} onChange={setAnnualExpenses} min={0} thousandSeparator="." decimalSeparator="," />
                <NumberInput label="Contributo annuo" value={annualContribution} onChange={setAnnualContribution} min={0} thousandSeparator="." decimalSeparator="," />
                <NumberInput
                  label="Safe withdrawal rate (%)"
                  value={safeWithdrawalRate}
                  onChange={setSafeWithdrawalRate}
                  min={0.1}
                  max={20}
                  step={0.01}
                  decimalScale={2}
                  fixedDecimalScale
                />
                <NumberInput label="Età attuale" value={currentAge} onChange={setCurrentAge} min={18} max={100} allowDecimal={false} />
                <NumberInput label="Età FIRE target" value={targetAge} onChange={setTargetAge} min={18} max={100} allowDecimal={false} />
              </SimpleGrid>
              <Group justify="space-between" align="center" wrap="wrap">
                <Text size="sm" c="dimmed">
                  Rendimento atteso usato per le stime deterministiche: {formatPct(expectedReturnPct, 1)} annuo.
                </Text>
                <Button color="red" onClick={handleSave} loading={settingsMutation.isPending || settingsLoading}>
                  Salva piano FIRE
                </Button>
              </Group>
            </Stack>
          </Card>
        </SimpleGrid>

        {(summaryLoading || monteCarloLoading) && portfolioId != null && (
          <Card withBorder radius="xl" padding="xl">
            <Group justify="center" py="xl">
              <Loader />
            </Group>
          </Card>
        )}

        <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }} spacing="lg">
          <StatCard
            icon={IconWallet}
            color="red"
            label="Patrimonio investibile"
            value={formatMoney(totalNetWorth, currency)}
            note={`${formatMoney(investedValue, currency)} investiti + ${formatMoney(cashBalance, currency)} liquidità`}
          />
          <StatCard
            icon={IconFlame}
            color="orange"
            label="Anni stimati al FIRE"
            value={estimatedYearsToFire != null ? `${estimatedYearsToFire.toFixed(1)} anni` : 'N/D'}
            note={estimatedFireAge != null ? `Età stimata ${estimatedFireAge.toFixed(1)}` : 'Configura spesa e SWR'}
          />
          <StatCard
            icon={IconTrendingUp}
            color="teal"
            label="Contributo richiesto"
            value={requiredContribution != null ? formatMoney(requiredContribution, currency) : 'N/D'}
            note={hasAgePlan ? 'Contributo annuo per arrivare entro l’età target' : 'Inserisci età attuale e target'}
          />
          <StatCard
            icon={IconTarget}
            color="blue"
            label="Capitale target"
            value={fireNumber != null ? formatMoney(fireNumber, currency) : 'N/D'}
            note={expensesValue > 0 ? `${formatMoney(expensesValue, currency)} / anno con SWR ${formatPct(swrValue, 2)}` : 'Imposta la spesa annua'}
          />
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="red" variant="light" radius="xl">
                  <IconFlame size={18} />
                </ThemeIcon>
                <Title order={4}>Lettura del piano</Title>
              </Group>
              <Text c="dimmed">
                {fireNumber == null
                  ? 'Inserisci una spesa annua e un withdrawal rate per ottenere la soglia FIRE.'
                  : fireGap === 0
                    ? 'Il portafoglio ha gia raggiunto o superato la soglia FIRE impostata.'
                    : estimatedYearsToFire != null
                      ? `Con il contributo annuo attuale e il rendimento medio stimato, la soglia FIRE viene raggiunta in circa ${estimatedYearsToFire.toFixed(1)} anni.`
                      : 'Con i dati attuali non è possibile stimare una traiettoria affidabile verso la soglia FIRE.'}
              </Text>
              {hasAgePlan && targetAgeValue > 0 && (
                <Alert color={estimatedFireAge != null && estimatedFireAge <= targetAgeValue ? 'teal' : 'yellow'} variant="light">
                  {estimatedFireAge != null
                    ? (estimatedFireAge <= targetAgeValue
                      ? `La stima attuale porta al FIRE prima o entro i ${targetAgeValue} anni.`
                      : `Con l'assetto attuale il FIRE stimato arriva dopo i ${targetAgeValue} anni.`)
                    : 'Serve completare il piano per confrontare l’età target.'}
                </Alert>
              )}
              <Table withTableBorder withColumnBorders>
                <Table.Tbody>
                  <Table.Tr><Table.Td>Portafoglio selezionato</Table.Td><Table.Td>{selectedPortfolio?.name ?? 'N/D'}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Base currency</Table.Td><Table.Td>{currency}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Rendimento atteso</Table.Td><Table.Td>{formatPct(expectedReturnPct, 1)}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Volatilità attesa</Table.Td><Table.Td>{formatPct(monteCarlo?.annualized_volatility_pct, 1)}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Spesa annua</Table.Td><Table.Td>{expensesValue > 0 ? formatMoney(expensesValue, currency) : 'N/D'}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Contributo annuo</Table.Td><Table.Td>{formatMoney(contributionValue, currency)}</Table.Td></Table.Tr>
                </Table.Tbody>
              </Table>
            </Stack>
          </Card>

          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="orange" variant="light" radius="xl">
                  <IconTrendingUp size={18} />
                </ThemeIcon>
                <Title order={4}>Scenari Monte Carlo</Title>
              </Group>
              <Text size="sm" c="dimmed">
                Lettura delle proiezioni sul capitale già investito. I valori sotto non includono nuovi versamenti futuri.
              </Text>
              {fireNumber == null || horizonScenarios.length === 0 ? (
                <Alert color="yellow" variant="light">
                  Servono una soglia FIRE configurata e dati Monte Carlo disponibili per confrontare gli orizzonti.
                </Alert>
              ) : isMobile ? (
                <Stack gap="sm">
                  {horizonScenarios.map((scenario) => (
                    <Card key={scenario.year} withBorder radius="lg" padding="md">
                      <Stack gap="xs">
                        <Group justify="space-between" align="flex-start">
                          <div>
                            <Text size="xs" tt="uppercase" fw={800} c="dimmed">Orizzonte</Text>
                            <Text fw={700}>{scenario.year} anni</Text>
                          </div>
                          <Badge color={scenario.onTrack ? 'teal' : (scenario.stretch ? 'yellow' : 'red')} variant="light">
                            {scenario.onTrack ? 'Target centrale raggiunto' : (scenario.stretch ? 'Scenario alto' : 'Sotto soglia')}
                          </Badge>
                        </Group>
                        <SimpleGrid cols={3} spacing="sm">
                          <ScenarioMetric label="P25" value={formatMoney(scenario.p25Value, currency)} />
                          <ScenarioMetric label="P50" value={formatMoney(scenario.p50Value, currency)} />
                          <ScenarioMetric label="P75" value={formatMoney(scenario.p75Value, currency)} />
                        </SimpleGrid>
                      </Stack>
                    </Card>
                  ))}
                </Stack>
              ) : (
                <Table withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Orizzonte</Table.Th>
                      <Table.Th>P25</Table.Th>
                      <Table.Th>P50</Table.Th>
                      <Table.Th>P75</Table.Th>
                      <Table.Th>Esito</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {horizonScenarios.map((scenario) => (
                      <Table.Tr key={scenario.year}>
                        <Table.Td>{scenario.year} anni</Table.Td>
                        <Table.Td>{formatMoney(scenario.p25Value, currency)}</Table.Td>
                        <Table.Td>{formatMoney(scenario.p50Value, currency)}</Table.Td>
                        <Table.Td>{formatMoney(scenario.p75Value, currency)}</Table.Td>
                        <Table.Td>
                          <Badge color={scenario.onTrack ? 'teal' : (scenario.stretch ? 'yellow' : 'red')} variant="light">
                            {scenario.onTrack ? 'Target centrale raggiunto' : (scenario.stretch ? 'Possibile nello scenario alto' : 'Sotto soglia')}
                          </Badge>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Stack>
          </Card>
        </SimpleGrid>
      </Stack>
    </PageLayout>
  );
}

function ScenarioMetric({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" tt="uppercase" fw={800} c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="sm">{value}</Text>
    </Stack>
  );
}

function HeroMetric({ label, value }: { label: string; value: string }) {
  return (
    <Card radius="lg" p="sm" style={{ background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.16)' }}>
      <Text size="xs" tt="uppercase" fw={800} style={{ opacity: 0.7 }}>{label}</Text>
      <Text fw={700}>{value}</Text>
    </Card>
  );
}

function StatCard({
  icon: Icon,
  color,
  label,
  value,
  note,
}: {
  icon: typeof IconFlame;
  color: string;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <Card withBorder radius="xl" padding="lg">
      <Stack gap="sm">
        <Group gap="sm">
          <ThemeIcon color={color} variant="light" radius="xl">
            <Icon size={18} />
          </ThemeIcon>
          <Text size="sm" fw={700}>{label}</Text>
        </Group>
        <Title order={3}>{value}</Title>
        <Text size="sm" c="dimmed">{note}</Text>
      </Stack>
    </Card>
  );
}
