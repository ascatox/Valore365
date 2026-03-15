import { useEffect, useMemo, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  Loader,
  Modal,
  NumberInput,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconFlame, IconRobot, IconTarget, IconTrendingUp, IconWallet } from '@tabler/icons-react';
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { MobileBottomNav } from '../components/mobile/MobileBottomNav';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { useAggregateDecumulationPlan, useDecumulationPlan, useMonteCarloProjection, usePortfolioSummary, usePortfolios, useUserSettings } from '../components/dashboard/hooks/queries';
import { getCopilotStatus, getMonteCarloProjection, getPortfolioSummary, type MonteCarloProjectionResponse, type PortfolioSummary, updateUserSettings } from '../services/api';

const PRIVACY_MASK = '******';

function isPrivacyModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
}

function formatMoney(value: number | null | undefined, currency = 'EUR'): string {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPct(value: number | null | undefined, digits = 1): string {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
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

type FireMode = 'accumulation' | 'decumulation';
type FireScopeMode = 'single' | 'aggregate';

export function FirePage() {
  const queryClient = useQueryClient();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [fireMode, setFireMode] = useState<FireMode>(() => {
    if (typeof window === 'undefined') return 'accumulation';
    const savedMode = window.localStorage.getItem(STORAGE_KEYS.fireMode);
    return savedMode === 'decumulation' ? 'decumulation' : 'accumulation';
  });
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });
  const [fireScopeMode, setFireScopeMode] = useState<FireScopeMode>(() => {
    if (typeof window === 'undefined') return 'single';
    const savedMode = window.localStorage.getItem(STORAGE_KEYS.fireScopeMode);
    return savedMode === 'aggregate' ? 'aggregate' : 'single';
  });
  const [aggregateSelectionOpened, setAggregateSelectionOpened] = useState(false);
  const [aggregatePortfolioIds, setAggregatePortfolioIds] = useState<string[]>(() => {
    if (typeof window === 'undefined') return [];
    const saved = window.localStorage.getItem(STORAGE_KEYS.fireAggregatePortfolioIds);
    if (!saved) return [];
    try {
      const parsed = JSON.parse(saved);
      return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : [];
    } catch {
      return [];
    }
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
  const [annualWithdrawal, setAnnualWithdrawal] = useState<number | string>(0);
  const [decumulationYears, setDecumulationYears] = useState<number | string>(30);
  const [inflationRate, setInflationRate] = useState<number | string>(2);
  const [otherIncomeAnnual, setOtherIncomeAnnual] = useState<number | string>(0);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copilotAvailable, setCopilotAvailable] = useState(false);
  const [copilotOpened, { open: openCopilot, close: closeCopilot }] = useDisclosure(false);

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
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.fireMode, fireMode);
  }, [fireMode]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.fireScopeMode, fireScopeMode);
  }, [fireScopeMode]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.fireAggregatePortfolioIds, JSON.stringify(aggregatePortfolioIds));
  }, [aggregatePortfolioIds]);

  useEffect(() => {
    if (!userSettings) return;
    setAnnualExpenses(userSettings.fire_annual_expenses ?? 0);
    setAnnualContribution(userSettings.fire_annual_contribution ?? 0);
    setSafeWithdrawalRate(userSettings.fire_safe_withdrawal_rate ?? 4);
    setCurrentAge(userSettings.fire_current_age ?? '');
    setTargetAge(userSettings.fire_target_age ?? '');
    setAnnualWithdrawal(userSettings.fire_annual_expenses ?? 0);
  }, [userSettings]);

  useEffect(() => {
    getCopilotStatus().then((s) => setCopilotAvailable(s.available)).catch(() => {});
  }, []);

  const fireQuickPrompts = useMemo(() => [
    'Quanto manca al FIRE?',
    'Il mio tasso di prelievo è sicuro?',
    'Come posso accelerare il percorso FIRE?',
    'Spiega le proiezioni Monte Carlo',
    'Cosa succede se aumento il contributo di 200€/mese?',
    'Il mio portafoglio può durare 30 anni in decumulo?',
  ], []);

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
  const availableAggregatePortfolios = useMemo(
    () => portfolios.filter((portfolio) => portfolio.base_currency === (selectedPortfolio?.base_currency ?? portfolios[0]?.base_currency)),
    [portfolios, selectedPortfolio],
  );

  useEffect(() => {
    if (!availableAggregatePortfolios.length) return;
    setAggregatePortfolioIds((previous) => {
      const existing = previous.filter((portfolioId) => availableAggregatePortfolios.some((portfolio) => String(portfolio.id) === portfolioId));
      if (existing.length > 0) return existing;
      if (selectedPortfolioId && availableAggregatePortfolios.some((portfolio) => String(portfolio.id) === selectedPortfolioId)) {
        return [selectedPortfolioId];
      }
      return [String(availableAggregatePortfolios[0].id)];
    });
  }, [availableAggregatePortfolios, selectedPortfolioId]);

  useEffect(() => {
    if (portfolios.length < 2 && fireScopeMode === 'aggregate') {
      setFireScopeMode('single');
    }
  }, [fireScopeMode, portfolios.length]);

  const aggregateSummaryQueries = useQueries({
    queries: fireScopeMode === 'aggregate'
      ? aggregatePortfolioIds.map((portfolioId) => ({
        queryKey: ['portfolio-summary', Number(portfolioId)],
        queryFn: () => getPortfolioSummary(Number(portfolioId)),
        enabled: aggregatePortfolioIds.length > 0,
      }))
      : [],
  });

  const aggregateMonteCarloQueries = useQueries({
    queries: fireScopeMode === 'aggregate'
      ? aggregatePortfolioIds.map((portfolioId) => ({
        queryKey: ['monte-carlo-projection', Number(portfolioId)],
        queryFn: () => getMonteCarloProjection(Number(portfolioId)),
        enabled: aggregatePortfolioIds.length > 0,
      }))
      : [],
  });

  const selectedAggregatePortfolios = useMemo(
    () => aggregatePortfolioIds
      .map((portfolioId) => portfolios.find((portfolio) => String(portfolio.id) === portfolioId) ?? null)
      .filter((portfolio): portfolio is NonNullable<typeof portfolio> => portfolio != null),
    [aggregatePortfolioIds, portfolios],
  );

  const aggregateSummaries = useMemo(
    () => aggregateSummaryQueries
      .map((query) => query.data ?? null)
      .filter((summaryData): summaryData is PortfolioSummary => summaryData != null),
    [aggregateSummaryQueries],
  );

  const aggregateMonteCarlo = useMemo(
    () => aggregateMonteCarloQueries
      .map((query) => query.data ?? null)
      .filter((projection): projection is MonteCarloProjectionResponse => projection != null),
    [aggregateMonteCarloQueries],
  );

  const aggregateSummaryLoading = aggregateSummaryQueries.some((query) => query.isLoading);
  const aggregateMonteCarloLoading = aggregateMonteCarloQueries.some((query) => query.isLoading);
  const aggregateSummaryError = aggregateSummaryQueries.find((query) => query.error)?.error;
  const aggregateMonteCarloError = aggregateMonteCarloQueries.find((query) => query.error)?.error;
  const expensesValue = typeof annualExpenses === 'number' ? annualExpenses : Number(annualExpenses || 0);
  const contributionValue = typeof annualContribution === 'number' ? annualContribution : Number(annualContribution || 0);
  const swrValue = typeof safeWithdrawalRate === 'number' ? safeWithdrawalRate : Number(safeWithdrawalRate || 0);
  const currentAgeValue = typeof currentAge === 'number' ? currentAge : Number(currentAge || 0);
  const targetAgeValue = typeof targetAge === 'number' ? targetAge : Number(targetAge || 0);
  const annualWithdrawalValue = typeof annualWithdrawal === 'number' ? annualWithdrawal : Number(annualWithdrawal || 0);
  const decumulationYearsValue = typeof decumulationYears === 'number' ? decumulationYears : Number(decumulationYears || 0);
  const inflationRateValue = typeof inflationRate === 'number' ? inflationRate : Number(inflationRate || 0);
  const otherIncomeAnnualValue = typeof otherIncomeAnnual === 'number' ? otherIncomeAnnual : Number(otherIncomeAnnual || 0);
  const decumulationEnabled = fireMode === 'decumulation' && annualWithdrawalValue > 0 && decumulationYearsValue > 0;
  const hasAgePlan = currentAgeValue > 0 && targetAgeValue > currentAgeValue;
  const fireNumber = expensesValue > 0 && swrValue > 0 ? expensesValue / (swrValue / 100) : null;

  const aggregateSummary = useMemo(() => {
    if (fireScopeMode !== 'aggregate' || !selectedAggregatePortfolios.length) return null;
    return aggregateSummaries.reduce<PortfolioSummary>((accumulator, current) => ({
      portfolio_id: 0,
      base_currency: current.base_currency,
      market_value: accumulator.market_value + current.market_value,
      cost_basis: accumulator.cost_basis + current.cost_basis,
      unrealized_pl: accumulator.unrealized_pl + current.unrealized_pl,
      unrealized_pl_pct: 0,
      day_change: accumulator.day_change + current.day_change,
      day_change_pct: 0,
      cash_balance: accumulator.cash_balance + current.cash_balance,
    }), {
      portfolio_id: 0,
      base_currency: selectedAggregatePortfolios[0]?.base_currency ?? 'EUR',
      market_value: 0,
      cost_basis: 0,
      unrealized_pl: 0,
      unrealized_pl_pct: 0,
      day_change: 0,
      day_change_pct: 0,
      cash_balance: 0,
    });
  }, [aggregateSummaries, fireScopeMode, selectedAggregatePortfolios]);
  const activeSummary = fireScopeMode === 'aggregate' ? aggregateSummary : (summary ?? null);
  const aggregateModeEnabled = fireScopeMode === 'aggregate' && selectedAggregatePortfolios.length > 0;
  const currency = activeSummary?.base_currency ?? selectedPortfolio?.base_currency ?? selectedAggregatePortfolios[0]?.base_currency ?? 'EUR';
  const investedValue = activeSummary?.market_value ?? 0;
  const cashBalance = activeSummary?.cash_balance ?? (fireScopeMode === 'aggregate' ? 0 : (selectedPortfolio?.cash_balance ?? 0));
  const totalNetWorth = investedValue + cashBalance;
  const coveragePct = fireNumber && fireNumber > 0 ? (totalNetWorth / fireNumber) * 100 : null;
  const fireGap = fireNumber != null ? Math.max(0, fireNumber - totalNetWorth) : null;

  const aggregateExpectedReturnPct = useMemo(() => {
    if (!aggregateMonteCarlo.length || !aggregateSummaries.length) return null;
    const totals = aggregateSummaries.reduce((sum, item) => sum + item.market_value + item.cash_balance, 0);
    if (totals <= 0) return null;
    return aggregateMonteCarlo.reduce((sum, projection) => {
      const matchingSummary = aggregateSummaries.find((summaryData) => summaryData.portfolio_id === projection.portfolio_id);
      const weight = matchingSummary ? (matchingSummary.market_value + matchingSummary.cash_balance) / totals : 0;
      return sum + projection.annualized_mean_return_pct * weight;
    }, 0);
  }, [aggregateMonteCarlo, aggregateSummaries]);

  const aggregateVolatilityPct = useMemo(() => {
    if (!aggregateMonteCarlo.length || !aggregateSummaries.length) return null;
    const totals = aggregateSummaries.reduce((sum, item) => sum + item.market_value + item.cash_balance, 0);
    if (totals <= 0) return null;
    return aggregateMonteCarlo.reduce((sum, projection) => {
      const matchingSummary = aggregateSummaries.find((summaryData) => summaryData.portfolio_id === projection.portfolio_id);
      const weight = matchingSummary ? (matchingSummary.market_value + matchingSummary.cash_balance) / totals : 0;
      return sum + projection.annualized_volatility_pct * weight;
    }, 0);
  }, [aggregateMonteCarlo, aggregateSummaries]);

  const aggregateHorizonScenarios = useMemo(() => {
    if (!aggregateMonteCarlo.length || fireNumber == null || !aggregateSummary) return [];
    const years = Array.from(new Set(
      aggregateMonteCarlo.flatMap((projection) => projection.projections.map((yearProjection) => yearProjection.year)),
    ))
      .filter((year) => year > 0)
      .sort((left, right) => left - right)
      .slice(0, 5);

    return years.map((year) => {
      const totals = aggregateMonteCarlo.reduce((accumulator, projection) => {
        const summaryData = aggregateSummaries.find((item) => item.portfolio_id === projection.portfolio_id);
        const yearlyProjection = projection.projections.find((item) => item.year === year);
        if (!summaryData || !yearlyProjection) return accumulator;
        return {
          p25Value: accumulator.p25Value + projectionToValue(yearlyProjection.p25, summaryData.market_value, summaryData.cash_balance),
          p50Value: accumulator.p50Value + projectionToValue(yearlyProjection.p50, summaryData.market_value, summaryData.cash_balance),
          p75Value: accumulator.p75Value + projectionToValue(yearlyProjection.p75, summaryData.market_value, summaryData.cash_balance),
        };
      }, { p25Value: 0, p50Value: 0, p75Value: 0 });

      return {
        year,
        ...totals,
        onTrack: totals.p50Value >= fireNumber,
        stretch: totals.p75Value >= fireNumber,
      };
    });
  }, [aggregateMonteCarlo, aggregateSummaries, aggregateSummary, fireNumber]);

  const expectedReturnPct = aggregateModeEnabled ? (aggregateExpectedReturnPct ?? 5) : (monteCarlo?.annualized_mean_return_pct ?? 5);
  const estimatedYearsToFire = fireNumber != null
    ? solveYearsToTarget(fireNumber, totalNetWorth, contributionValue, expectedReturnPct)
    : null;
  const estimatedFireAge = estimatedYearsToFire != null && currentAgeValue > 0 ? currentAgeValue + estimatedYearsToFire : null;
  const requiredContribution = hasAgePlan && fireNumber != null
    ? solveRequiredContribution(fireNumber, totalNetWorth, targetAgeValue - currentAgeValue, expectedReturnPct)
    : null;

  const singleHorizonScenarios = useMemo(() => {
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
  const horizonScenarios = aggregateModeEnabled ? aggregateHorizonScenarios : singleHorizonScenarios;
  const { data: decumulationData, isLoading: decumulationLoading, error: decumulationError } = useDecumulationPlan(
    portfolioId,
    {
      annualWithdrawal: Math.max(0, annualWithdrawalValue),
      years: Math.max(1, decumulationYearsValue),
      inflationRatePct: inflationRateValue,
      otherIncomeAnnual: Math.max(0, otherIncomeAnnualValue),
      currentAge: currentAgeValue > 0 ? currentAgeValue : null,
    },
    decumulationEnabled && !aggregateModeEnabled,
  );
  const aggregatePortfolioIdNumbers = useMemo(
    () => selectedAggregatePortfolios.map((portfolio) => portfolio.id),
    [selectedAggregatePortfolios],
  );
  const {
    data: aggregateDecumulationData,
    isLoading: aggregateDecumulationLoading,
    error: aggregateDecumulationError,
  } = useAggregateDecumulationPlan(
    aggregatePortfolioIdNumbers,
    {
      annualWithdrawal: Math.max(0, annualWithdrawalValue),
      years: Math.max(1, decumulationYearsValue),
      inflationRatePct: inflationRateValue,
      otherIncomeAnnual: Math.max(0, otherIncomeAnnualValue),
      currentAge: currentAgeValue > 0 ? currentAgeValue : null,
    },
    decumulationEnabled && aggregateModeEnabled,
  );

  const activeDecumulationData = aggregateModeEnabled ? aggregateDecumulationData : decumulationData;
  const decumulationPlan = activeDecumulationData?.projections ?? [];
  const sustainableWithdrawal = activeDecumulationData?.sustainable_withdrawal ?? null;
  const capitalDurationYears = aggregateModeEnabled
    ? (aggregateDecumulationData?.depletion_year_p50 ?? decumulationPlan.length)
    : (decumulationData?.depletion_year_p50 ?? decumulationPlan.length);
  const decumulationSuccess = aggregateModeEnabled
    ? ((aggregateDecumulationData?.success_rate_pct ?? 0) >= 70)
    : ((decumulationData?.success_rate_pct ?? 0) >= 70);
  const firstCriticalYear = decumulationPlan.find((year) => year.p50_effective_withdrawal_rate_pct >= swrValue) ?? null;
  const withdrawalCoveragePct = annualWithdrawalValue > 0
    ? Math.min(999, (((activeDecumulationData?.annual_other_income ?? 0) + (sustainableWithdrawal ?? 0)) / annualWithdrawalValue) * 100)
    : null;

  const summaryLoadingState = aggregateModeEnabled ? aggregateSummaryLoading : summaryLoading;
  const monteCarloLoadingState = aggregateModeEnabled ? aggregateMonteCarloLoading : monteCarloLoading;
  const summaryErrorState = aggregateModeEnabled ? aggregateSummaryError : summaryError;
  const activeVolatilityPct = aggregateModeEnabled ? aggregateVolatilityPct : (monteCarlo?.annualized_volatility_pct ?? null);
  const fireScopeLabel = aggregateModeEnabled
    ? `${selectedAggregatePortfolios.length} portafogli inclusi`
    : (selectedPortfolio?.name ?? 'N/D');
  const incompatiblePortfolioCount = portfolios.length - availableAggregatePortfolios.length;

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
      <Stack gap="lg" pb={isMobile ? 96 : 0}>
        <PageHeader
          eyebrow="Indipendenza finanziaria e piano di decumulo"
          title="FIRE"
          description="Stimatore operativo per Financial Independence, con soglia FIRE, traiettoria attesa e scenari di raggiungimento."
          actions={(
            fireScopeMode === 'single' ? (
              <PortfolioSwitcher
                portfolios={portfolios}
                value={selectedPortfolioId}
                onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
                loading={portfoliosLoading}
                style={{ width: '100%', maxWidth: 360 }}
              />
            ) : (
              <Button variant="default" onClick={() => setAggregateSelectionOpened(true)}>
                {`Perimetro FIRE: ${selectedAggregatePortfolios.length}`}
              </Button>
            )
          )}
        />

        {(summaryErrorState instanceof Error) && <Alert color="red">{summaryErrorState.message}</Alert>}
        {(aggregateMonteCarloError instanceof Error) && fireScopeMode === 'aggregate' && fireMode === 'accumulation' && <Alert color="red">{aggregateMonteCarloError.message}</Alert>}
        {saveMessage && <Alert color="teal">{saveMessage}</Alert>}
        {saveError && <Alert color="red">{saveError}</Alert>}
        {((aggregateModeEnabled ? aggregateDecumulationError : decumulationError) instanceof Error) && fireMode === 'decumulation' && (
          <Alert color="red">{(aggregateModeEnabled ? aggregateDecumulationError : decumulationError)?.message}</Alert>
        )}
        {aggregateModeEnabled && incompatiblePortfolioCount > 0 && (
          <Alert color="yellow" variant="light">
            Il perimetro aggregato supporta per ora solo portafogli con la stessa valuta base. {incompatiblePortfolioCount} portafogli restano esclusi dalla selezione.
          </Alert>
        )}

        <Group justify="space-between" align="center" wrap="wrap">
          <SegmentedControl
            value={fireScopeMode}
            onChange={(value) => setFireScopeMode(value as FireScopeMode)}
            data={[
              { label: 'Portafoglio', value: 'single' },
              { label: 'Aggregato', value: 'aggregate', disabled: portfolios.length < 2 },
            ]}
          />
          <Text size="sm" c="dimmed">
            {fireScopeMode === 'single'
              ? 'Vista FIRE su un singolo portafoglio.'
              : `${selectedAggregatePortfolios.length} portafogli nel perimetro FIRE.`}
          </Text>
        </Group>

        {!isMobile && (
          <Group justify="space-between" align="center" wrap="wrap">
            <Tabs value={fireMode} onChange={(value) => setFireMode((value as FireMode) ?? 'accumulation')} variant="default">
              <Tabs.List
                style={{
                  flexWrap: 'nowrap',
                  overflowX: 'auto',
                  overflowY: 'hidden',
                  WebkitOverflowScrolling: 'touch',
                  scrollbarWidth: 'none',
                  paddingBottom: 0,
                  gap: 0,
                }}
              >
                <Tabs.Tab value="accumulation">
                  <Text span>Accumulo</Text>
                </Tabs.Tab>
                <Tabs.Tab value="decumulation">
                  <Text span>Decumulo</Text>
                </Tabs.Tab>
              </Tabs.List>
            </Tabs>
            <Text size="sm" c="dimmed">
              {fireMode === 'accumulation'
                ? 'Modalità orientata al raggiungimento della soglia FIRE.'
                : 'Modalità orientata alla sostenibilità dei prelievi nel tempo.'}
            </Text>
          </Group>
        )}

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
                  <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.72 }}>
                    {fireMode === 'accumulation' ? 'FIRE Target' : 'Piano di Decumulo'}
                  </Text>
                  <Title order={1} mt={6} c="white" style={{ fontSize: 'clamp(2.8rem, 7vw, 5rem)', lineHeight: 0.95 }}>
                    {fireMode === 'accumulation'
                      ? (fireNumber != null ? formatMoney(fireNumber, currency) : '—')
                      : (sustainableWithdrawal != null ? formatMoney(sustainableWithdrawal, currency) : '—')}
                  </Title>
                  <Text c="rgba(255,255,255,0.82)" mt="sm" size="lg">
                    {fireMode === 'accumulation'
                      ? `Patrimonio attuale ${formatMoney(totalNetWorth, currency)}`
                      : `Capitale iniziale ${formatMoney(totalNetWorth, currency)}`}
                  </Text>
                  <Text c="rgba(255,255,255,0.72)" mt={6} size="sm">
                    {fireScopeMode === 'aggregate' ? `Perimetro FIRE aggregato · ${fireScopeLabel}` : `Portafoglio attivo · ${fireScopeLabel}`}
                  </Text>
                </div>
                <Badge
                  size="xl"
                  radius="sm"
                  color={
                    fireMode === 'accumulation'
                      ? (coveragePct != null && coveragePct >= 100 ? 'teal' : 'red')
                      : (decumulationSuccess ? 'teal' : 'yellow')
                  }
                  variant="filled"
                  styles={{
                    root: { color: '#ffffff' },
                    label: { color: '#ffffff' },
                  }}
                >
                  {isPrivacyModeEnabled()
                    ? PRIVACY_MASK
                    : fireMode === 'accumulation'
                      ? (coveragePct != null ? `${Math.min(999, coveragePct).toFixed(0)}% coperto` : 'Configura il piano')
                      : (decumulationSuccess ? 'Piano sostenibile' : 'Piano da rivedere')}
                </Badge>
              </Group>

              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                {fireMode === 'accumulation' ? (
                  <>
                    <HeroMetric label="Spesa annua" value={expensesValue > 0 ? formatMoney(expensesValue, currency) : '—'} />
                    <HeroMetric label="SWR" value={swrValue > 0 ? formatPct(swrValue, 2) : '—'} />
                    <HeroMetric label="Gap" value={fireGap != null ? formatMoney(fireGap, currency) : '—'} />
                    <HeroMetric label="ETA" value={estimatedYearsToFire != null ? `${Math.ceil(estimatedYearsToFire)} anni` : 'N/D'} />
                  </>
                ) : (
                  <>
                    <HeroMetric label="Prelievo" value={annualWithdrawalValue > 0 ? formatMoney(annualWithdrawalValue, currency) : '—'} />
                    <HeroMetric label="Altri redditi" value={formatMoney(otherIncomeAnnualValue, currency)} />
                    <HeroMetric label="Inflazione" value={formatPct(inflationRateValue, 1)} />
                    <HeroMetric label="Durata" value={capitalDurationYears > 0 ? `${capitalDurationYears} anni` : 'N/D'} />
                  </>
                )}
              </SimpleGrid>

              <Stack gap={8}>
                <Group justify="space-between">
                  <Text size="sm" c="rgba(255,255,255,0.82)">
                    {fireMode === 'accumulation' ? 'Avanzamento verso la soglia FIRE' : 'Copertura del prelievo richiesto'}
                  </Text>
                  <Text size="sm" fw={700} c="white">
                    {isPrivacyModeEnabled()
                      ? PRIVACY_MASK
                      : fireMode === 'accumulation'
                        ? (coveragePct != null ? `${Math.min(100, coveragePct).toFixed(1)}%` : 'N/D')
                        : (withdrawalCoveragePct != null ? `${Math.min(100, withdrawalCoveragePct).toFixed(1)}%` : 'N/D')}
                  </Text>
                </Group>
                <Progress
                  value={Math.max(0, Math.min(100, fireMode === 'accumulation' ? (coveragePct ?? 0) : (withdrawalCoveragePct ?? 0)))}
                  color={fireMode === 'accumulation' ? 'red' : 'teal'}
                  radius="xl"
                  size="lg"
                />
              </Stack>
            </Stack>
          </Card>

          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="red" variant="light" radius="xl">
                  <IconTarget size={18} />
                </ThemeIcon>
                <Title order={4}>{fireMode === 'accumulation' ? 'Ipotesi del piano' : 'Ipotesi di decumulo'}</Title>
              </Group>
              {fireMode === 'accumulation' ? (
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
              ) : (
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  <NumberInput label="Prelievo annuo lordo" value={annualWithdrawal} onChange={setAnnualWithdrawal} min={0} thousandSeparator="." decimalSeparator="," />
                  <NumberInput label="Altri redditi annui" value={otherIncomeAnnual} onChange={setOtherIncomeAnnual} min={0} thousandSeparator="." decimalSeparator="," />
                  <NumberInput
                    label="Orizzonte di decumulo (anni)"
                    value={decumulationYears}
                    onChange={setDecumulationYears}
                    min={1}
                    max={80}
                    allowDecimal={false}
                  />
                  <NumberInput
                    label="Inflazione spesa (%)"
                    value={inflationRate}
                    onChange={setInflationRate}
                    min={0}
                    max={20}
                    step={0.1}
                    decimalScale={1}
                    fixedDecimalScale
                  />
                  <NumberInput label="Età attuale" value={currentAge} onChange={setCurrentAge} min={18} max={100} allowDecimal={false} />
                  <NumberInput
                    label="Safe withdrawal rate di guardrail (%)"
                    value={safeWithdrawalRate}
                    onChange={setSafeWithdrawalRate}
                    min={0.1}
                    max={20}
                    step={0.01}
                    decimalScale={2}
                    fixedDecimalScale
                  />
                </SimpleGrid>
              )}
              <Group justify="space-between" align="center" wrap="wrap">
                <Text size="sm" c="dimmed">
                  Rendimento atteso usato per le stime deterministiche: {formatPct(expectedReturnPct, 1)} annuo.
                  {aggregateModeEnabled && fireMode === 'decumulation' ? ' In modalità aggregata il decumulo usa un Monte Carlo reale sul perimetro selezionato.' : ''}
                </Text>
                <Button color="red" onClick={handleSave} loading={settingsMutation.isPending || settingsLoading}>
                  Salva piano FIRE
                </Button>
              </Group>
            </Stack>
          </Card>
        </SimpleGrid>

        {(summaryLoadingState || monteCarloLoadingState || decumulationLoading || aggregateDecumulationLoading) && (portfolioId != null || aggregateModeEnabled) && (
          <Card withBorder radius="xl" padding="xl">
            <Group justify="center" py="xl">
              <Loader />
            </Group>
          </Card>
        )}

        <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }} spacing="lg">
          {fireMode === 'accumulation' ? (
            <>
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
            </>
          ) : (
            <>
              <StatCard
                icon={IconWallet}
                color="red"
                label="Capitale iniziale"
                value={formatMoney(totalNetWorth, currency)}
                note={`${formatMoney(investedValue, currency)} investiti + ${formatMoney(cashBalance, currency)} liquidità`}
              />
              <StatCard
                icon={IconFlame}
                color="orange"
                label="Durata stimata"
                value={capitalDurationYears > 0 ? `${capitalDurationYears} anni` : 'N/D'}
                note={activeDecumulationData?.depletion_year_p50 ? 'Esaurimento mediano entro l’orizzonte simulato' : 'Capitale mediano ancora positivo a fine orizzonte'}
              />
              <StatCard
                icon={IconTrendingUp}
                color="teal"
                label="Reddito sostenibile"
                value={sustainableWithdrawal != null ? formatMoney(sustainableWithdrawal, currency) : 'N/D'}
                note={`Success rate ${formatPct(activeDecumulationData?.success_rate_pct, 1)}`}
              />
              <StatCard
                icon={IconTarget}
                color="blue"
                label="Primo anno critico"
                value={firstCriticalYear ? `Anno ${firstCriticalYear.year}` : 'Nessuno'}
                note={firstCriticalYear ? `WR mediano ${formatPct(firstCriticalYear.p50_effective_withdrawal_rate_pct, 2)}` : `Guardrail ${formatPct(swrValue, 2)}`}
              />
            </>
          )}
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="red" variant="light" radius="xl">
                  <IconFlame size={18} />
                </ThemeIcon>
                <Title order={4}>{fireMode === 'accumulation' ? 'Lettura del piano' : 'Lettura del decumulo'}</Title>
              </Group>
              <Text c="dimmed">
                {fireMode === 'accumulation'
                  ? (fireNumber == null
                    ? 'Inserisci una spesa annua e un withdrawal rate per ottenere la soglia FIRE.'
                    : fireGap === 0
                      ? 'Il portafoglio ha gia raggiunto o superato la soglia FIRE impostata.'
                      : estimatedYearsToFire != null
                        ? `Con il contributo annuo attuale e il rendimento medio stimato, la soglia FIRE viene raggiunta in circa ${estimatedYearsToFire.toFixed(1)} anni.`
                        : 'Con i dati attuali non è possibile stimare una traiettoria affidabile verso la soglia FIRE.')
                  : (annualWithdrawalValue <= 0
                      ? 'Inserisci un prelievo annuo per valutare la sostenibilità del decumulo.'
                    : decumulationPlan.length === 0
                    ? (aggregateModeEnabled
                        ? 'Con i dati attuali non è possibile costruire una simulazione Monte Carlo aggregata di decumulo.'
                        : 'Con i dati attuali non è possibile costruire una simulazione Monte Carlo di decumulo.')
                      : decumulationSuccess
                        ? (aggregateModeEnabled
                          ? `Con le ipotesi correnti la probabilità di chiudere l’orizzonte con capitale residuo sul perimetro aggregato è circa ${activeDecumulationData?.success_rate_pct?.toFixed(1) ?? '0'}%.`
                          : `Con le ipotesi correnti la probabilità di chiudere l’orizzonte con capitale residuo è circa ${activeDecumulationData?.success_rate_pct?.toFixed(1) ?? '0'}%.`)
                        : `Con le ipotesi correnti la probabilità di esaurimento entro l’orizzonte è circa ${activeDecumulationData?.depletion_probability_pct?.toFixed(1) ?? '0'}%.`)}
              </Text>
              {fireMode === 'accumulation' && hasAgePlan && targetAgeValue > 0 && (
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
                  <Table.Tr><Table.Td>Perimetro FIRE</Table.Td><Table.Td>{fireScopeLabel}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Base currency</Table.Td><Table.Td>{currency}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Rendimento atteso</Table.Td><Table.Td>{formatPct(expectedReturnPct, 1)}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Volatilità attesa</Table.Td><Table.Td>{formatPct(activeVolatilityPct, 1)}</Table.Td></Table.Tr>
                  {fireMode === 'accumulation' ? (
                    <>
                      <Table.Tr><Table.Td>Spesa annua</Table.Td><Table.Td>{expensesValue > 0 ? formatMoney(expensesValue, currency) : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Contributo annuo</Table.Td><Table.Td>{formatMoney(contributionValue, currency)}</Table.Td></Table.Tr>
                    </>
                  ) : (
                    <>
                      <Table.Tr><Table.Td>Prelievo annuo</Table.Td><Table.Td>{annualWithdrawalValue > 0 ? formatMoney(annualWithdrawalValue, currency) : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Altri redditi annui</Table.Td><Table.Td>{formatMoney(otherIncomeAnnualValue, currency)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Inflazione spesa</Table.Td><Table.Td>{formatPct(inflationRateValue, 1)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Orizzonte</Table.Td><Table.Td>{decumulationYearsValue > 0 ? `${decumulationYearsValue} anni` : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Success rate</Table.Td><Table.Td>{formatPct(activeDecumulationData?.success_rate_pct, 1)}</Table.Td></Table.Tr>
                    </>
                  )}
                </Table.Tbody>
              </Table>
              {aggregateModeEnabled && (
                <>
                  <Divider />
                  <Stack gap="xs">
                    <Text size="sm" fw={700}>Composizione perimetro FIRE</Text>
                    {selectedAggregatePortfolios.map((portfolio) => (
                      <Group key={portfolio.id} justify="space-between" wrap="nowrap">
                        <Text size="sm">{portfolio.name}</Text>
                        <Text size="sm" c="dimmed">{portfolio.base_currency}</Text>
                      </Group>
                    ))}
                  </Stack>
                </>
              )}
            </Stack>
          </Card>

          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="orange" variant="light" radius="xl">
                  <IconTrendingUp size={18} />
                </ThemeIcon>
                <Title order={4}>{fireMode === 'accumulation' ? 'Scenari Monte Carlo' : 'Timeline di decumulo'}</Title>
              </Group>
                <Text size="sm" c="dimmed">
                {fireMode === 'accumulation'
                  ? 'Lettura delle proiezioni sul capitale già investito. I valori sotto non includono nuovi versamenti futuri.'
                  : 'Simulazione Monte Carlo anno per anno del capitale residuo, con prelievi indicizzati all’inflazione.'}
                </Text>
              {fireMode === 'accumulation' ? (
                fireNumber == null || horizonScenarios.length === 0 ? (
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
                )
              ) : decumulationPlan.length === 0 ? (
                <Alert color="yellow" variant="light">
                  Inserisci prelievo annuo e orizzonte per costruire una timeline di decumulo.
                </Alert>
              ) : isMobile ? (
                <Stack gap="sm">
                  {decumulationPlan.slice(0, 8).map((year) => (
                    <Card key={year.year} withBorder radius="lg" padding="md">
                      <Stack gap="xs">
                        <Group justify="space-between" align="flex-start">
                          <div>
                            <Text size="xs" tt="uppercase" fw={800} c="dimmed">Anno</Text>
                            <Text fw={700}>
                              {year.year}
                              {year.age != null ? ` · età ${year.age}` : ''}
                            </Text>
                          </div>
                          <Badge color={year.depletion_probability_pct >= 50 ? 'red' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'yellow' : 'teal')} variant="light">
                            {year.depletion_probability_pct >= 50 ? 'Rischio alto' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'Anno critico' : 'Sostenibile')}
                          </Badge>
                        </Group>
                        <SimpleGrid cols={3} spacing="sm">
                          <ScenarioMetric label="Prelievo" value={formatMoney(year.net_withdrawal, currency)} />
                          <ScenarioMetric label="P50 Finale" value={formatMoney(year.p50_ending_capital, currency)} />
                          <ScenarioMetric label="Rischio" value={formatPct(year.depletion_probability_pct, 1)} />
                        </SimpleGrid>
                      </Stack>
                    </Card>
                  ))}
                </Stack>
              ) : (
                <Table withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Anno</Table.Th>
                      <Table.Th>Età</Table.Th>
                      <Table.Th>Prelievo lordo</Table.Th>
                      <Table.Th>Prelievo netto</Table.Th>
                      <Table.Th>WR mediano</Table.Th>
                      <Table.Th>Capitale finale P50</Table.Th>
                      <Table.Th>Esito</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {decumulationPlan.map((year) => (
                      <Table.Tr key={year.year}>
                        <Table.Td>{year.year}</Table.Td>
                        <Table.Td>{year.age ?? 'N/D'}</Table.Td>
                        <Table.Td>{formatMoney(year.gross_withdrawal, currency)}</Table.Td>
                        <Table.Td>{formatMoney(year.net_withdrawal, currency)}</Table.Td>
                        <Table.Td>{formatPct(year.p50_effective_withdrawal_rate_pct, 2)}</Table.Td>
                        <Table.Td>{formatMoney(year.p50_ending_capital, currency)}</Table.Td>
                        <Table.Td>
                          <Badge color={year.depletion_probability_pct >= 50 ? 'red' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'yellow' : 'teal')} variant="light">
                            {year.depletion_probability_pct >= 50 ? 'Fragile' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'Critico' : 'OK')}
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

        {isMobile && (
          <MobileBottomNav
            items={[
              { value: 'accumulation', label: 'Accumulo', icon: IconTrendingUp },
              { value: 'decumulation', label: 'Decumulo', icon: IconWallet },
            ]}
            value={fireMode}
            onChange={(value) => setFireMode(value as FireMode)}
            bottomOffset={12}
          />
        )}
      </Stack>
      <Modal
        opened={aggregateSelectionOpened}
        onClose={() => setAggregateSelectionOpened(false)}
        title="Perimetro FIRE aggregato"
        size="lg"
        centered
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Seleziona i portafogli da includere nel calcolo FIRE aggregato. In questa fase sono supportati solo portafogli con la stessa valuta base.
          </Text>
          <Group gap="sm">
            <Button
              variant="default"
              size="xs"
              onClick={() => setAggregatePortfolioIds(availableAggregatePortfolios.map((portfolio) => String(portfolio.id)))}
            >
              Seleziona tutti
            </Button>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => setAggregatePortfolioIds(selectedPortfolioId ? [selectedPortfolioId] : [])}
            >
              Solo attivo
            </Button>
          </Group>
          <Stack gap="xs">
            {availableAggregatePortfolios.map((portfolio) => {
              const portfolioId = String(portfolio.id);
              const checked = aggregatePortfolioIds.includes(portfolioId);
              return (
                <Checkbox
                  key={portfolio.id}
                  checked={checked}
                  onChange={(event) => {
                    if (event.currentTarget.checked) {
                      setAggregatePortfolioIds((previous) => Array.from(new Set([...previous, portfolioId])));
                      return;
                    }
                    setAggregatePortfolioIds((previous) => {
                      const next = previous.filter((value) => value !== portfolioId);
                      return next.length > 0 ? next : previous;
                    });
                  }}
                  label={`${portfolio.name} · ${portfolio.base_currency}`}
                  description={`Cash ${formatMoney(portfolio.cash_balance ?? 0, portfolio.base_currency)}`}
                />
              );
            })}
          </Stack>
          <Alert color="red" variant="light">
            Patrimonio FIRE incluso: {selectedAggregatePortfolios.length} portafogli · {formatMoney(totalNetWorth, currency)}
          </Alert>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAggregateSelectionOpened(false)}>Chiudi</Button>
          </Group>
        </Stack>
      </Modal>

      {copilotAvailable && (
        <ActionIcon
          variant="filled"
          color="teal"
          size={52}
          radius="xl"
          onClick={openCopilot}
          aria-label="Apri FIRE Copilot"
          style={{
            position: 'fixed',
            bottom: isMobile ? 80 : 24,
            right: 24,
            zIndex: 100,
            boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
          }}
        >
          <IconRobot size={24} />
        </ActionIcon>
      )}

      <CopilotChat
        opened={copilotOpened}
        onClose={closeCopilot}
        portfolioId={aggregateModeEnabled ? aggregatePortfolioIdNumbers[0] ?? portfolioId : portfolioId}
        portfolioIds={aggregateModeEnabled ? aggregatePortfolioIdNumbers : undefined}
        title="FIRE Copilot"
        quickPrompts={fireQuickPrompts}
        emptyStateDescription="Ti aiuto a capire il tuo percorso verso l'indipendenza finanziaria. Ecco qualche spunto:"
      />
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
      <Text size="xs" tt="uppercase" fw={800} c="rgba(255,255,255,0.7)">{label}</Text>
      <Text fw={700} c="white">{value}</Text>
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
