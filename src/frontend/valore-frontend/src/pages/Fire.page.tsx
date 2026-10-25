import { useEffect, useMemo, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
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
  TextInput,
  ThemeIcon,
  Title,
  Tooltip as MantineTooltip,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { IconFlame, IconPlus, IconRobot, IconTarget, IconTrash, IconTrendingUp, IconWallet } from '@tabler/icons-react';
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { useAggregateDecumulationPlan, useDecumulationPlan, useMonteCarloProjection, usePortfolioSummary, usePortfolios, useUserSettings } from '../components/dashboard/hooks/queries';
import { getCopilotStatus, getMonteCarloProjection, getPortfolioSummary, type DecumulationYearProjection, type FireOneOffExpense, type MonteCarloProjectionResponse, type PortfolioSummary, updateUserSettings } from '../services/api';
import { computeFireTarget, estimateYearsToFire, solveRequiredContribution, type AccumulationInput } from '../components/fire/accumulation';
import { useSwipeTabs } from '../hooks/useSwipeTabs';

const PRIVACY_MASK = '******';
const DEFAULT_FIRE_EXPECTED_RETURN_PCT = 5;

function isPrivacyModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
}

function formatMoney(value: number | null | undefined, currency = 'EUR'): string {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return new Intl.NumberFormat('it-IT', {
    useGrouping: 'always',
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

function projectionToValue(indexValue: number, investedValue: number, cashBalance: number): number {
  return (indexValue / 100) * investedValue + cashBalance;
}

function getDecumulationOutcomeTooltip(
  riskProbabilityPct: number,
  effectiveWithdrawalRatePct: number,
  guardrailPct: number,
  floorEnabled = false,
): string {
  if (riskProbabilityPct >= 50) {
    return floorEnabled
      ? `Sotto soglia: probabilità ${riskProbabilityPct.toFixed(1)}% di essere già scesi sotto il capitale minimo.`
      : `Rischio elevato: probabilità di esaurimento ${riskProbabilityPct.toFixed(1)}%.`;
  }
  if (effectiveWithdrawalRatePct >= guardrailPct) {
    return `Anno critico: WR mediano ${effectiveWithdrawalRatePct.toFixed(2)}%, sopra il guardrail ${guardrailPct.toFixed(2)}%.`;
  }
  return `Scenario sostenibile: WR mediano ${effectiveWithdrawalRatePct.toFixed(2)}%, sotto il guardrail ${guardrailPct.toFixed(2)}%.`;
}

type FireMode = 'accumulation' | 'decumulation';
type FireScopeMode = 'single' | 'aggregate';

// Order of the mode tabs, for swiping between them on mobile.
const FIRE_MODES = ['accumulation', 'decumulation'] as const;

export function FirePage() {
  const queryClient = useQueryClient();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
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
  const [expectedReturnPctInput, setExpectedReturnPctInput] = useState<number | string>(DEFAULT_FIRE_EXPECTED_RETURN_PCT);
  const [safeWithdrawalRate, setSafeWithdrawalRate] = useState<number | string>(4);
  const [currentAge, setCurrentAge] = useState<number | string>('');
  const [targetAge, setTargetAge] = useState<number | string>('');
  const [annualWithdrawal, setAnnualWithdrawal] = useState<number | string>(0);
  const [decumulationYears, setDecumulationYears] = useState<number | string>(30);
  const [inflationRate, setInflationRate] = useState<number | string>(2);
  const [otherIncomeAnnual, setOtherIncomeAnnual] = useState<number | string>(0);
  const [capitalGainsTaxRate, setCapitalGainsTaxRate] = useState<number | string>(26);
  const [capitalFloor, setCapitalFloor] = useState<number | string>(0);
  const [contributionGrowthPct, setContributionGrowthPct] = useState<number | string>(0);
  const [pensionAnnual, setPensionAnnual] = useState<number | string>(0);
  const [pensionStartAge, setPensionStartAge] = useState<number | string>('');
  const [oneOffExpenses, setOneOffExpenses] = useState<FireOneOffExpense[]>([]);
  const [terminalTargetMin, setTerminalTargetMin] = useState<number | string>(0);
  const [terminalTargetMax, setTerminalTargetMax] = useState<number | string>(0);
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
    setExpectedReturnPctInput(userSettings.fire_expected_return_pct ?? DEFAULT_FIRE_EXPECTED_RETURN_PCT);
    setSafeWithdrawalRate(userSettings.fire_safe_withdrawal_rate ?? 4);
    setCapitalGainsTaxRate(userSettings.fire_capital_gains_tax_rate ?? 26);
    setCurrentAge(userSettings.fire_current_age ?? '');
    setTargetAge(userSettings.fire_target_age ?? '');
    setAnnualWithdrawal(userSettings.fire_annual_expenses ?? 0);
    setCapitalFloor(userSettings.fire_capital_floor ?? 0);
    setContributionGrowthPct(userSettings.fire_contribution_growth_pct ?? 0);
    setPensionAnnual(userSettings.fire_pension_annual ?? 0);
    setPensionStartAge(userSettings.fire_pension_start_age ?? '');
    setOneOffExpenses(userSettings.fire_one_off_expenses ?? []);
    setTerminalTargetMin(userSettings.fire_terminal_target_min ?? 0);
    setTerminalTargetMax(userSettings.fire_terminal_target_max ?? 0);
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
  const configuredExpectedReturnPct = typeof expectedReturnPctInput === 'number' ? expectedReturnPctInput : Number(expectedReturnPctInput || 0);
  const swrValue = typeof safeWithdrawalRate === 'number' ? safeWithdrawalRate : Number(safeWithdrawalRate || 0);
  const currentAgeValue = typeof currentAge === 'number' ? currentAge : Number(currentAge || 0);
  const targetAgeValue = typeof targetAge === 'number' ? targetAge : Number(targetAge || 0);
  const annualWithdrawalValue = typeof annualWithdrawal === 'number' ? annualWithdrawal : Number(annualWithdrawal || 0);
  const decumulationYearsValue = typeof decumulationYears === 'number' ? decumulationYears : Number(decumulationYears || 0);
  const inflationRateValue = typeof inflationRate === 'number' ? inflationRate : Number(inflationRate || 0);
  const otherIncomeAnnualValue = typeof otherIncomeAnnual === 'number' ? otherIncomeAnnual : Number(otherIncomeAnnual || 0);
  const capitalGainsTaxRateValue = typeof capitalGainsTaxRate === 'number' ? capitalGainsTaxRate : Number(capitalGainsTaxRate || 0);
  const capitalFloorValue = Math.max(0, typeof capitalFloor === 'number' ? capitalFloor : Number(capitalFloor || 0));
  const contributionGrowthPctValue = Math.max(0, typeof contributionGrowthPct === 'number' ? contributionGrowthPct : Number(contributionGrowthPct || 0));
  const pensionAnnualValue = Math.max(0, typeof pensionAnnual === 'number' ? pensionAnnual : Number(pensionAnnual || 0));
  const pensionStartAgeValue = typeof pensionStartAge === 'number' ? pensionStartAge : Number(pensionStartAge || 0);
  const terminalTargetMinValue = Math.max(0, typeof terminalTargetMin === 'number' ? terminalTargetMin : Number(terminalTargetMin || 0));
  const terminalTargetMaxValue = Math.max(0, typeof terminalTargetMax === 'number' ? terminalTargetMax : Number(terminalTargetMax || 0));
  const terminalRangeInvalid = terminalTargetMaxValue > 0 && terminalTargetMaxValue < terminalTargetMinValue;
  const validOneOffExpenses = useMemo(
    () => oneOffExpenses.filter((expense) => expense.age >= 18 && expense.amount > 0),
    [oneOffExpenses],
  );
  const decumulationEnabled = fireMode === 'decumulation' && annualWithdrawalValue > 0 && decumulationYearsValue > 0;
  const hasAgePlan = currentAgeValue > 0 && targetAgeValue > currentAgeValue;

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
  const expectedReturnPct = configuredExpectedReturnPct > 0 ? configuredExpectedReturnPct : DEFAULT_FIRE_EXPECTED_RETURN_PCT;
  const accumulationInput: AccumulationInput = {
    annualExpenses: expensesValue,
    safeWithdrawalRatePct: swrValue,
    capitalFloor: capitalFloorValue,
    pensionAnnual: pensionAnnualValue,
    pensionStartAge: pensionStartAgeValue > 0 ? pensionStartAgeValue : null,
    oneOffExpenses: validOneOffExpenses,
    currentAge: currentAgeValue > 0 ? currentAgeValue : null,
    startCapital: totalNetWorth,
    annualContribution: contributionValue,
    contributionGrowthPct: contributionGrowthPctValue,
    annualReturnPct: expectedReturnPct,
  };
  const estimatedYearsToFire = estimateYearsToFire(accumulationInput);
  const estimatedFireAge = estimatedYearsToFire != null && currentAgeValue > 0 ? currentAgeValue + estimatedYearsToFire : null;
  const requiredContribution = hasAgePlan ? solveRequiredContribution(accumulationInput, targetAgeValue) : null;
  const plannedFireAge = hasAgePlan
    ? targetAgeValue
    : (estimatedYearsToFire != null && currentAgeValue > 0 ? currentAgeValue + Math.ceil(estimatedYearsToFire) : null);
  const fireTarget = computeFireTarget(accumulationInput, plannedFireAge);
  const fireNumber = fireTarget?.total ?? null;
  const coveragePct = fireNumber && fireNumber > 0 ? (totalNetWorth / fireNumber) * 100 : null;
  const fireGap = fireNumber != null ? Math.max(0, fireNumber - totalNetWorth) : null;

  const aggregateMonteCarloMeanReturnPct = useMemo(() => {
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
    const targetYears = aggregateMonteCarlo[0]?.horizons ?? [5, 10, 20];
    const years = Array.from(new Set(
      aggregateMonteCarlo.flatMap((projection) => projection.projections.map((yearProjection) => yearProjection.year)),
    ))
      .filter((year) => targetYears.includes(year))
      .sort((left, right) => left - right);

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

  const monteCarloMeanReturnPct = aggregateModeEnabled ? aggregateMonteCarloMeanReturnPct : (monteCarlo?.annualized_mean_return_pct ?? null);
  const singleHorizonScenarios = useMemo(() => {
    if (!monteCarlo || fireNumber == null) return [];
    const targetYears = monteCarlo.horizons ?? [5, 10, 20];
    return monteCarlo.projections
      .filter((projection) => targetYears.includes(projection.year))
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
      });
  }, [cashBalance, fireNumber, investedValue, monteCarlo]);
  const horizonScenarios = aggregateModeEnabled ? aggregateHorizonScenarios : singleHorizonScenarios;

  const monteCarloChartData = useMemo(() => {
    if (!monteCarlo || monteCarlo.projections.length === 0) return [];
    return monteCarlo.projections.map((p) => ({
      year: `${p.year}`,
      p10: p.p10,
      p25: p.p25,
      p50: p.p50,
      p75: p.p75,
      p90: p.p90,
    }));
  }, [monteCarlo]);

  const decumulationScheduleParams = useMemo(() => ({
    capitalFloor: capitalFloorValue,
    pensionAnnual: pensionAnnualValue,
    pensionStartAge: pensionStartAgeValue > 0 ? pensionStartAgeValue : null,
    oneOffExpenses: validOneOffExpenses.map(({ age, amount }) => ({ age, amount })),
    // An inverted range is shown as an input error and not sent to the API.
    terminalTargetMin: terminalRangeInvalid ? 0 : terminalTargetMinValue,
    terminalTargetMax: terminalRangeInvalid ? 0 : terminalTargetMaxValue,
  }), [capitalFloorValue, pensionAnnualValue, pensionStartAgeValue, validOneOffExpenses, terminalRangeInvalid, terminalTargetMinValue, terminalTargetMaxValue]);
  const { data: decumulationData, isLoading: decumulationLoading, error: decumulationError } = useDecumulationPlan(
    portfolioId,
    {
      annualWithdrawal: Math.max(0, annualWithdrawalValue),
      years: Math.max(1, decumulationYearsValue),
      inflationRatePct: inflationRateValue,
      otherIncomeAnnual: Math.max(0, otherIncomeAnnualValue),
      capitalGainsTaxRatePct: Math.max(0, capitalGainsTaxRateValue),
      currentAge: currentAgeValue > 0 ? currentAgeValue : null,
      ...decumulationScheduleParams,
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
      capitalGainsTaxRatePct: Math.max(0, capitalGainsTaxRateValue),
      currentAge: currentAgeValue > 0 ? currentAgeValue : null,
      ...decumulationScheduleParams,
    },
    decumulationEnabled && aggregateModeEnabled,
  );

  const activeDecumulationData = aggregateModeEnabled ? aggregateDecumulationData : decumulationData;
  const decumulationPlan = activeDecumulationData?.projections ?? [];
  const sustainableWithdrawal = activeDecumulationData?.sustainable_withdrawal ?? null;
  const estimatedEmbeddedGainRatioPct = activeDecumulationData?.estimated_embedded_gain_ratio_pct ?? null;
  const firstYearProjection = decumulationPlan[0] ?? null;
  const capitalDurationYears = aggregateModeEnabled
    ? (aggregateDecumulationData?.depletion_year_p50 ?? decumulationPlan.length)
    : (decumulationData?.depletion_year_p50 ?? decumulationPlan.length);
  const decumulationSuccess = aggregateModeEnabled
    ? ((aggregateDecumulationData?.success_rate_pct ?? 0) >= 70)
    : ((decumulationData?.success_rate_pct ?? 0) >= 70);
  const floorEnabled = capitalFloorValue > 0 && activeDecumulationData != null && activeDecumulationData.capital_floor > 0;
  const terminalRangeEnabled = activeDecumulationData?.terminal_in_range_probability_pct != null;
  const terminalRangeLabel = terminalTargetMaxValue > 0
    ? `tra ${formatMoney(terminalTargetMinValue, currency)} e ${formatMoney(terminalTargetMaxValue, currency)}`
    : `sopra ${formatMoney(terminalTargetMinValue, currency)}`;
  const yearRiskPct = (year: DecumulationYearProjection) => (floorEnabled ? year.floor_breach_probability_pct : year.depletion_probability_pct);
  const firstCriticalYear = decumulationPlan.find((year) => year.p50_effective_withdrawal_rate_pct >= swrValue) ?? null;
  const withdrawalCoveragePct = annualWithdrawalValue > 0
    ? Math.min(999, ((sustainableWithdrawal ?? 0) / annualWithdrawalValue) * 100)
    : null;

  const summaryLoadingState = aggregateModeEnabled ? aggregateSummaryLoading : summaryLoading;
  const monteCarloLoadingState = aggregateModeEnabled ? aggregateMonteCarloLoading : monteCarloLoading;
  const summaryErrorState = aggregateModeEnabled ? aggregateSummaryError : summaryError;
  const activeVolatilityPct = aggregateModeEnabled ? aggregateVolatilityPct : (monteCarlo?.annualized_volatility_pct ?? null);
  const fireScopeLabel = aggregateModeEnabled
    ? `${selectedAggregatePortfolios.length} portafogli inclusi`
    : (selectedPortfolio?.name ?? 'N/D');
  const incompatiblePortfolioCount = portfolios.length - availableAggregatePortfolios.length;

  const swipeRef = useSwipeTabs({
    tabs: FIRE_MODES,
    active: fireMode,
    onChange: (mode) => setFireMode(mode as FireMode),
    enabled: !!isMobile,
  });

  const handleSave = () => {
    setSaveMessage(null);
    setSaveError(null);
    settingsMutation.mutate({
      fire_annual_expenses: Math.max(0, expensesValue || 0),
      fire_annual_contribution: Math.max(0, contributionValue || 0),
      fire_expected_return_pct: Math.max(0.1, expectedReturnPct || DEFAULT_FIRE_EXPECTED_RETURN_PCT),
      fire_safe_withdrawal_rate: Math.max(0.1, swrValue || 4),
      fire_capital_gains_tax_rate: Math.max(0, capitalGainsTaxRateValue || 0),
      fire_current_age: currentAgeValue > 0 ? currentAgeValue : null,
      fire_target_age: targetAgeValue > 0 ? targetAgeValue : null,
      fire_capital_floor: capitalFloorValue,
      fire_contribution_growth_pct: Math.min(20, contributionGrowthPctValue),
      fire_pension_annual: pensionAnnualValue,
      fire_pension_start_age: pensionStartAgeValue > 0 ? pensionStartAgeValue : null,
      fire_one_off_expenses: validOneOffExpenses,
      fire_terminal_target_min: terminalTargetMinValue,
      fire_terminal_target_max: terminalRangeInvalid ? 0 : terminalTargetMaxValue,
    });
  };

  return (
    <PageLayout>
      <Stack gap="lg" ref={swipeRef}>
        <PageHeader
          eyebrow="Indipendenza finanziaria e piano di decumulo"
          title="FIRE"
          description="Stimatore operativo per Financial Independence, con soglia FIRE, traiettoria attesa e scenari di raggiungimento."
          actions={(
            fireScopeMode === 'single' ? (
              <PortfolioSwitcher
                portfolios={portfolios}
                value={selectedPortfolioId}
                selectedPortfolioCashBalance={summary?.cash_balance ?? null}
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

        <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
          <Card
            radius="xl"
            padding="xl"
            withBorder
            style={{ background: 'linear-gradient(140deg, #083634 0%, #0b4a46 56%, #c2620a 170%)', color: 'white' }}
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
                      ? (coveragePct != null && coveragePct >= 100 ? 'teal' : 'orange')
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
                    <HeroMetric label="Spesa annua netta" value={expensesValue > 0 ? formatMoney(expensesValue, currency) : '—'} />
                    <HeroMetric label="SWR" value={swrValue > 0 ? formatPct(swrValue, 2) : '—'} />
                    <HeroMetric label="Gap" value={fireGap != null ? formatMoney(fireGap, currency) : '—'} />
                    <HeroMetric label="ETA" value={estimatedYearsToFire != null ? `${Math.ceil(estimatedYearsToFire)} anni` : 'N/D'} />
                  </>
                ) : (
                  <>
                    <HeroMetric label="Spesa netta" value={annualWithdrawalValue > 0 ? formatMoney(annualWithdrawalValue, currency) : '—'} />
                    <HeroMetric label="Altri redditi" value={formatMoney(otherIncomeAnnualValue, currency)} />
                    <HeroMetric label="Tasse" value={formatPct(capitalGainsTaxRateValue, 1)} />
                    <HeroMetric label="Durata" value={capitalDurationYears > 0 ? `${capitalDurationYears} anni` : 'N/D'} />
                  </>
                )}
              </SimpleGrid>

              <Stack gap={8}>
                <Group justify="space-between">
                  <Text size="sm" c="rgba(255,255,255,0.82)">
                    {fireMode === 'accumulation' ? 'Avanzamento verso la soglia FIRE' : 'Copertura della spesa netta richiesta'}
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
                  color={fireMode === 'accumulation' ? 'orange' : 'teal'}
                  radius="xl"
                  size="lg"
                />
              </Stack>
            </Stack>
          </Card>

          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="orange" variant="light" radius="xl">
                  <IconTarget size={18} />
                </ThemeIcon>
                <Title order={4}>{fireMode === 'accumulation' ? 'Ipotesi del piano' : 'Ipotesi di decumulo'}</Title>
              </Group>
              {fireMode === 'accumulation' ? (
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  <NumberInput label="Spesa annua netta target" value={annualExpenses} onChange={setAnnualExpenses} min={0} thousandSeparator="." decimalSeparator="," />
                  <NumberInput label="Contributo annuo" value={annualContribution} onChange={setAnnualContribution} min={0} thousandSeparator="." decimalSeparator="," />
                  <NumberInput
                    label="Rendimento atteso annuo (%)"
                    value={expectedReturnPctInput}
                    onChange={setExpectedReturnPctInput}
                    min={0.1}
                    max={20}
                    step={0.1}
                    decimalScale={1}
                    fixedDecimalScale
                  />
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
                  <NumberInput
                    label="Crescita annua contributo (%)"
                    description="Aumento del contributo ogni anno"
                    value={contributionGrowthPct}
                    onChange={setContributionGrowthPct}
                    min={0}
                    max={20}
                    step={0.5}
                    decimalScale={1}
                  />
                  <NumberInput
                    label="Capitale minimo da preservare"
                    description="In euro di oggi: il capitale non deve mai scendere sotto questa soglia"
                    value={capitalFloor}
                    onChange={setCapitalFloor}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                  />
                  <NumberInput
                    label="Pensione annua netta"
                    description="In euro di oggi, indicizzata all'inflazione"
                    value={pensionAnnual}
                    onChange={setPensionAnnual}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                  />
                  <NumberInput
                    label="Età inizio pensione"
                    description={pensionAnnualValue > 0 && currentAgeValue <= 0 ? "Serve l'età attuale per collocare la pensione" : 'Vuoto = pensione già attiva'}
                    value={pensionStartAge}
                    onChange={setPensionStartAge}
                    min={18}
                    max={100}
                    allowDecimal={false}
                  />
                </SimpleGrid>
              ) : (
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  <NumberInput label="Spesa annua netta desiderata" value={annualWithdrawal} onChange={setAnnualWithdrawal} min={0} thousandSeparator="." decimalSeparator="," />
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
                  <NumberInput
                    label="Tassa plusvalenze (%)"
                    value={capitalGainsTaxRate}
                    onChange={setCapitalGainsTaxRate}
                    min={0}
                    max={100}
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
                  <NumberInput
                    label="Capitale minimo da preservare"
                    description="In euro di oggi: il capitale non deve mai scendere sotto questa soglia"
                    value={capitalFloor}
                    onChange={setCapitalFloor}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                  />
                  <NumberInput
                    label="Capitale finale desiderato: minimo"
                    description="In euro di oggi: quanto vuoi avere almeno alla fine dell'orizzonte"
                    value={terminalTargetMin}
                    onChange={setTerminalTargetMin}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                  />
                  <NumberInput
                    label="Capitale finale desiderato: massimo"
                    description="In euro di oggi: oltre questa cifra avresti potuto spendere di più (0 = nessun limite)"
                    value={terminalTargetMax}
                    onChange={setTerminalTargetMax}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                    error={terminalRangeInvalid ? 'Il massimo deve essere almeno pari al minimo' : undefined}
                  />
                  <NumberInput
                    label="Pensione annua netta"
                    description="In euro di oggi, indicizzata all'inflazione"
                    value={pensionAnnual}
                    onChange={setPensionAnnual}
                    min={0}
                    thousandSeparator="."
                    decimalSeparator=","
                  />
                  <NumberInput
                    label="Età inizio pensione"
                    description={pensionAnnualValue > 0 && currentAgeValue <= 0 ? "Serve l'età attuale per collocare la pensione" : 'Vuoto = pensione già attiva'}
                    value={pensionStartAge}
                    onChange={setPensionStartAge}
                    min={18}
                    max={100}
                    allowDecimal={false}
                  />
                </SimpleGrid>
              )}
              <OneOffExpensesEditor
                expenses={oneOffExpenses}
                onChange={setOneOffExpenses}
                currentAge={currentAgeValue > 0 ? currentAgeValue : null}
              />
              <Group justify="space-between" align="center" wrap="wrap">
                <Text size="sm" c="dimmed">
                  Rendimento atteso usato per le stime deterministiche: {formatPct(expectedReturnPct, 1)} annuo.
                  {fireMode === 'accumulation' && monteCarloMeanReturnPct != null ? ` Monte Carlo attuale: ${formatPct(monteCarloMeanReturnPct, 1)} annuo.` : ''}
                  {fireMode === 'decumulation' ? ` Fiscalità stimata: ${formatPct(capitalGainsTaxRateValue, 1)} sulle plusvalenze.` : ''}
                  {aggregateModeEnabled && fireMode === 'decumulation' ? ' In modalità aggregata il decumulo usa un Monte Carlo reale sul perimetro selezionato.' : ''}
                </Text>
                <Button onClick={handleSave} loading={settingsMutation.isPending || settingsLoading}>
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
                color="teal"
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
                note={hasAgePlan ? "Contributo annuo per arrivare entro l'età target" : 'Inserisci età attuale e target'}
              />
              <StatCard
                icon={IconTarget}
                color="blue"
                label="Capitale target"
                value={fireNumber != null ? formatMoney(fireNumber, currency) : 'N/D'}
                note={fireTarget
                  ? (fireTarget.total > fireTarget.spendingCapital
                    ? `${formatMoney(fireTarget.spendingCapital, currency)} per le spese + ${formatMoney(fireTarget.total - fireTarget.spendingCapital, currency)} tra soglia, ponte pensione e spese una tantum`
                    : `${formatMoney(expensesValue, currency)} / anno netti con SWR ${formatPct(swrValue, 2)}`)
                  : 'Imposta la spesa annua netta'}
              />
            </>
          ) : (
            <>
              <StatCard
                icon={IconWallet}
                color="teal"
                label="Capitale iniziale"
                value={formatMoney(totalNetWorth, currency)}
                note={`${formatMoney(investedValue, currency)} investiti + ${formatMoney(cashBalance, currency)} liquidità`}
              />
              <StatCard
                icon={IconFlame}
                color="orange"
                label={floorEnabled ? 'Anni sopra la soglia' : 'Durata stimata'}
                value={floorEnabled
                  ? `${activeDecumulationData?.floor_breach_year_p50 ? activeDecumulationData.floor_breach_year_p50 - 1 : decumulationPlan.length} anni`
                  : (capitalDurationYears > 0 ? `${capitalDurationYears} anni` : 'N/D')}
                note={floorEnabled
                  ? (activeDecumulationData?.floor_breach_year_p50
                    ? `Il capitale mediano scende sotto ${formatMoney(capitalFloorValue, currency)} (oggi) nell'anno ${activeDecumulationData.floor_breach_year_p50}`
                    : 'Capitale mediano sempre sopra la soglia')
                  : (activeDecumulationData?.depletion_year_p50 ? "Esaurimento mediano entro l'orizzonte simulato" : 'Capitale mediano ancora positivo a fine orizzonte')}
              />
              <StatCard
                icon={IconTrendingUp}
                color="teal"
                label="Spesa sostenibile netta"
                value={sustainableWithdrawal != null ? formatMoney(sustainableWithdrawal, currency) : 'N/D'}
                note={`Success rate ${formatPct(activeDecumulationData?.success_rate_pct, 1)}`}
              />
              <StatCard
                icon={IconTarget}
                color="blue"
                label="Tasse stimate anno 1"
                value={firstYearProjection ? formatMoney(firstYearProjection.estimated_taxes, currency) : 'N/D'}
                note={firstYearProjection ? `Lordo richiesto ${formatMoney(firstYearProjection.gross_withdrawal, currency)}` : `Guardrail ${formatPct(swrValue, 2)}`}
              />
            </>
          )}
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
          <Card withBorder radius="xl" padding="lg">
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="orange" variant="light" radius="xl">
                  <IconFlame size={18} />
                </ThemeIcon>
                <Title order={4}>{fireMode === 'accumulation' ? 'Lettura del piano' : 'Lettura del decumulo'}</Title>
              </Group>
              <Text c="dimmed">
                {fireMode === 'accumulation'
                  ? (fireNumber == null
                    ? 'Inserisci una spesa annua netta e un withdrawal rate per ottenere la soglia FIRE.'
                    : fireGap === 0
                      ? 'Il portafoglio ha gia raggiunto o superato la soglia FIRE impostata.'
                      : estimatedYearsToFire != null
                        ? `Con il contributo annuo attuale e il rendimento atteso di lungo periodo, la soglia FIRE viene raggiunta in circa ${estimatedYearsToFire.toFixed(1)} anni.`
                        : 'Con i dati attuali non è possibile stimare una traiettoria affidabile verso la soglia FIRE.')
                  : (annualWithdrawalValue <= 0
                      ? 'Inserisci una spesa netta annua per valutare la sostenibilità fiscale del decumulo.'
                    : decumulationPlan.length === 0
                    ? (aggregateModeEnabled
                        ? 'Con i dati attuali non è possibile costruire una simulazione Monte Carlo aggregata di decumulo.'
                        : 'Con i dati attuali non è possibile costruire una simulazione Monte Carlo di decumulo.')
                      : floorEnabled
                        ? `Con le ipotesi correnti la probabilità di restare sempre sopra il capitale minimo di ${formatMoney(capitalFloorValue, currency)} (euro di oggi) per tutto l'orizzonte è circa ${activeDecumulationData?.success_rate_pct?.toFixed(1) ?? '0'}%.`
                      : decumulationSuccess
                        ? (aggregateModeEnabled
                          ? `Con le ipotesi correnti la probabilità di chiudere l'orizzonte con capitale residuo sul perimetro aggregato è circa ${activeDecumulationData?.success_rate_pct?.toFixed(1) ?? '0'}%.`
                          : `Con le ipotesi correnti la probabilità di chiudere l'orizzonte con capitale residuo è circa ${activeDecumulationData?.success_rate_pct?.toFixed(1) ?? '0'}%.`)
                        : `Con le ipotesi correnti la probabilità di esaurimento entro l'orizzonte è circa ${activeDecumulationData?.depletion_probability_pct?.toFixed(1) ?? '0'}%.`)}
              </Text>
              {fireMode === 'decumulation' && firstYearProjection && (
                <Alert color={firstCriticalYear ? 'yellow' : 'blue'} variant="light">
                  {`Con tassa plusvalenze ${formatPct(capitalGainsTaxRateValue, 1)} e quota plusvalenze stimata ${formatPct(estimatedEmbeddedGainRatioPct, 1)}, il primo anno richiede ${formatMoney(firstYearProjection.gross_withdrawal, currency)} lordi dal portafoglio per sostenere ${formatMoney(firstYearProjection.net_spending_after_tax, currency)} netti complessivi.`}
                  {firstCriticalYear ? ` Il guardrail SWR viene toccato entro l'anno ${firstCriticalYear.year}.` : ''}
                </Alert>
              )}
              {fireMode === 'decumulation' && terminalRangeEnabled && activeDecumulationData && (
                <Alert color={(activeDecumulationData.terminal_in_range_probability_pct ?? 0) >= 50 ? 'teal' : 'yellow'} variant="light">
                  {`Probabilità di chiudere l'orizzonte con un capitale ${terminalRangeLabel} (euro di oggi): ${formatPct(activeDecumulationData.terminal_in_range_probability_pct, 1)}`}
                  {` · sotto ${formatPct(activeDecumulationData.terminal_below_range_probability_pct, 1)}`}
                  {terminalTargetMaxValue > 0 ? ` · sopra ${formatPct(activeDecumulationData.terminal_above_range_probability_pct, 1)}` : ''}
                  {`. Capitale finale mediano ${formatMoney(activeDecumulationData.p50_terminal_value_real, currency)} in euro di oggi.`}
                  {activeDecumulationData.withdrawal_for_terminal_max != null
                    ? ` Per finire nell'intervallo la spesa netta sostenibile va da ${formatMoney(activeDecumulationData.withdrawal_for_terminal_max, currency)} a ${formatMoney(activeDecumulationData.sustainable_withdrawal, currency)} l'anno.`
                    : ''}
                </Alert>
              )}
              {fireMode === 'accumulation' && hasAgePlan && targetAgeValue > 0 && (
                <Alert color={estimatedFireAge != null && estimatedFireAge <= targetAgeValue ? 'teal' : 'yellow'} variant="light">
                  {estimatedFireAge != null
                    ? (estimatedFireAge <= targetAgeValue
                      ? `La stima attuale porta al FIRE prima o entro i ${targetAgeValue} anni.`
                      : `Con l'assetto attuale il FIRE stimato arriva dopo i ${targetAgeValue} anni.`)
                    : "Serve completare il piano per confrontare l'età target."}
                </Alert>
              )}
              <Table withTableBorder withColumnBorders>
                <Table.Tbody>
                  <Table.Tr><Table.Td>Perimetro FIRE</Table.Td><Table.Td>{fireScopeLabel}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Base currency</Table.Td><Table.Td>{currency}</Table.Td></Table.Tr>
                  <Table.Tr><Table.Td>Rendimento atteso</Table.Td><Table.Td>{formatPct(expectedReturnPct, 1)}</Table.Td></Table.Tr>
                  {fireMode === 'accumulation' && monteCarloMeanReturnPct != null && (
                    <Table.Tr><Table.Td>Rendimento atteso (ipotesi lungo periodo)</Table.Td><Table.Td>{formatPct(monteCarloMeanReturnPct, 1)}</Table.Td></Table.Tr>
                  )}
                  <Table.Tr><Table.Td>Volatilità attesa</Table.Td><Table.Td>{formatPct(activeVolatilityPct, 1)}</Table.Td></Table.Tr>
                  {fireMode === 'accumulation' ? (
                    <>
                      <Table.Tr><Table.Td>Spesa annua netta</Table.Td><Table.Td>{expensesValue > 0 ? formatMoney(expensesValue, currency) : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Contributo annuo</Table.Td><Table.Td>{formatMoney(contributionValue, currency)}</Table.Td></Table.Tr>
                      {contributionGrowthPctValue > 0 && (
                        <Table.Tr><Table.Td>Crescita annua contributo</Table.Td><Table.Td>{formatPct(contributionGrowthPctValue, 1)}</Table.Td></Table.Tr>
                      )}
                      {fireTarget && (
                        <>
                          <Table.Tr><Table.Td>Capitale per le spese (SWR)</Table.Td><Table.Td>{formatMoney(fireTarget.spendingCapital, currency)}</Table.Td></Table.Tr>
                          {fireTarget.capitalFloor > 0 && (
                            <Table.Tr><Table.Td>Capitale minimo da preservare</Table.Td><Table.Td>{formatMoney(fireTarget.capitalFloor, currency)}</Table.Td></Table.Tr>
                          )}
                          {fireTarget.pensionBridge > 0 && (
                            <Table.Tr><Table.Td>Ponte fino alla pensione ({pensionStartAgeValue} anni)</Table.Td><Table.Td>{formatMoney(fireTarget.pensionBridge, currency)}</Table.Td></Table.Tr>
                          )}
                          {fireTarget.oneOffReserve > 0 && (
                            <Table.Tr><Table.Td>Riserva spese una tantum dopo il FIRE</Table.Td><Table.Td>{formatMoney(fireTarget.oneOffReserve, currency)}</Table.Td></Table.Tr>
                          )}
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      <Table.Tr><Table.Td>Spesa netta target</Table.Td><Table.Td>{annualWithdrawalValue > 0 ? formatMoney(annualWithdrawalValue, currency) : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Altri redditi annui</Table.Td><Table.Td>{formatMoney(otherIncomeAnnualValue, currency)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Tassa plusvalenze</Table.Td><Table.Td>{formatPct(capitalGainsTaxRateValue, 1)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Quota plusvalenze stimata</Table.Td><Table.Td>{formatPct(estimatedEmbeddedGainRatioPct, 1)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Inflazione spesa</Table.Td><Table.Td>{formatPct(inflationRateValue, 1)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Orizzonte</Table.Td><Table.Td>{decumulationYearsValue > 0 ? `${decumulationYearsValue} anni` : 'N/D'}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Spesa sostenibile netta</Table.Td><Table.Td>{formatMoney(sustainableWithdrawal, currency)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Success rate</Table.Td><Table.Td>{formatPct(activeDecumulationData?.success_rate_pct, 1)}</Table.Td></Table.Tr>
                      {floorEnabled && (
                        <>
                          <Table.Tr><Table.Td>Capitale minimo (euro di oggi)</Table.Td><Table.Td>{formatMoney(capitalFloorValue, currency)}</Table.Td></Table.Tr>
                          <Table.Tr><Table.Td>Probabilità di scendere sotto la soglia</Table.Td><Table.Td>{formatPct(activeDecumulationData?.floor_breach_probability_pct, 1)}</Table.Td></Table.Tr>
                          <Table.Tr><Table.Td>Anno mediano sotto la soglia</Table.Td><Table.Td>{activeDecumulationData?.floor_breach_year_p50 ? `Anno ${activeDecumulationData.floor_breach_year_p50}` : 'Mai entro l\'orizzonte'}</Table.Td></Table.Tr>
                        </>
                      )}
                      {(activeDecumulationData?.pension_annual ?? 0) > 0 && (
                        <Table.Tr><Table.Td>Pensione</Table.Td><Table.Td>{`${formatMoney(activeDecumulationData?.pension_annual, currency)} / anno dall'anno ${activeDecumulationData?.pension_start_year ?? 1}`}</Table.Td></Table.Tr>
                      )}
                      {terminalRangeEnabled && (
                        <>
                          <Table.Tr><Table.Td>Capitale finale desiderato (euro di oggi)</Table.Td><Table.Td>{terminalTargetMaxValue > 0 ? `${formatMoney(terminalTargetMinValue, currency)} – ${formatMoney(terminalTargetMaxValue, currency)}` : `≥ ${formatMoney(terminalTargetMinValue, currency)}`}</Table.Td></Table.Tr>
                          <Table.Tr><Table.Td>Capitale finale mediano (euro di oggi)</Table.Td><Table.Td>{formatMoney(activeDecumulationData?.p50_terminal_value_real, currency)}</Table.Td></Table.Tr>
                          <Table.Tr><Table.Td>Probabilità di finire nell'intervallo</Table.Td><Table.Td>{formatPct(activeDecumulationData?.terminal_in_range_probability_pct, 1)}</Table.Td></Table.Tr>
                          {activeDecumulationData?.withdrawal_for_terminal_max != null && (
                            <Table.Tr><Table.Td>Spesa netta per finire nell'intervallo</Table.Td><Table.Td>{`${formatMoney(activeDecumulationData.withdrawal_for_terminal_max, currency)} – ${formatMoney(activeDecumulationData.sustainable_withdrawal, currency)}`}</Table.Td></Table.Tr>
                          )}
                        </>
                      )}
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
                  ? `Proiezioni sul capitale già investito basate su ${(monteCarlo?.num_simulations ?? 5000).toLocaleString('it-IT', { useGrouping: 'always' })} simulazioni Monte Carlo. I valori sotto non includono nuovi versamenti futuri.`
                  : `Simulazione Monte Carlo (${(activeDecumulationData?.num_simulations ?? 5000).toLocaleString('it-IT', { useGrouping: 'always' })} percorsi) anno per anno del capitale residuo, con spesa netta indicizzata all'inflazione e fiscalità stimata sulle plusvalenze.`}
                </Text>
              {fireMode === 'accumulation' && monteCarloChartData.length > 0 && (() => {
                const tealColor = theme.colors.teal[isDark ? 4 : 6];
                const lightTeal = theme.colors.teal[isDark ? 9 : 1];
                const midTeal = theme.colors.teal[isDark ? 8 : 2];
                const mv = (investedValue ?? 0) + (cashBalance ?? 0);
                const hasValue = mv > 0;
                return (
                  <Box style={{ width: '100%', height: 320, overflow: 'hidden' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={monteCarloChartData} margin={{ top: 10, right: isMobile ? 5 : 10, left: isMobile ? -15 : 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={isDark ? theme.colors.dark[4] : '#e2e8f0'} />
                        <XAxis
                          dataKey="year"
                          tick={{ fontSize: isMobile ? 10 : 12 }}
                          tickFormatter={(v) => v === '0' ? 'Oggi' : `${v}a`}
                        />
                        <YAxis
                          yAxisId="left"
                          tick={{ fontSize: isMobile ? 10 : 12 }}
                          tickFormatter={(v: number) => `${v}`}
                          domain={['auto', 'auto']}
                          width={isMobile ? 35 : 60}
                        />
                        {hasValue && !isMobile && (
                          <YAxis
                            yAxisId="right"
                            orientation="right"
                            tick={{ fontSize: 11 }}
                            tickFormatter={(v: number) =>
                              ((v / 100) * mv).toLocaleString('it-IT', { useGrouping: 'always', style: 'currency', currency: currency, minimumFractionDigits: 0, maximumFractionDigits: 0 })
                            }
                            domain={['auto', 'auto']}
                          />
                        )}
                        <RechartsTooltip
                          content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const d = payload[0]?.payload as { year: string; p10: number; p25: number; p50: number; p75: number; p90: number };
                            const fmtGrowth = (v: number) => { const pct = v - 100; return pct >= 0 ? `+${pct.toFixed(0)}%` : `${pct.toFixed(0)}%`; };
                            const fmtVal = (v: number) => ((v / 100) * mv).toLocaleString('it-IT', { useGrouping: 'always', style: 'currency', currency: currency, minimumFractionDigits: 0, maximumFractionDigits: 0 });
                            return (
                              <Box style={{ background: isDark ? theme.colors.dark[7] : 'white', border: `1px solid ${isDark ? theme.colors.dark[4] : '#e2e8f0'}`, borderRadius: 8, padding: '8px 12px' }}>
                                <Text fw={700} size="sm" mb={4}>{d.year === '0' ? 'Oggi' : `Anno ${d.year}`}</Text>
                                {[
                                  { label: 'P90', val: d.p90 },
                                  { label: 'P75', val: d.p75 },
                                  { label: 'P50', val: d.p50, bold: true },
                                  { label: 'P25', val: d.p25 },
                                  { label: 'P10', val: d.p10 },
                                ].map(({ label, val, bold }) => (
                                  <Text key={label} size="xs" c={bold ? undefined : 'dimmed'} fw={bold ? 600 : undefined}>
                                    {label}: {fmtGrowth(val)}{hasValue && ` (${fmtVal(val)})`}
                                  </Text>
                                ))}
                              </Box>
                            );
                          }}
                        />
                        <ReferenceLine yAxisId="left" y={100} stroke={isDark ? theme.colors.dark[3] : '#94a3b8'} strokeDasharray="4 4" />
                        <Area yAxisId="left" type="monotone" dataKey="p90" stroke="none" fill={lightTeal} fillOpacity={0.5} isAnimationActive={false} />
                        <Area yAxisId="left" type="monotone" dataKey="p75" stroke="none" fill={midTeal} fillOpacity={0.5} isAnimationActive={false} />
                        <Area yAxisId="left" type="monotone" dataKey="p25" stroke="none" fill={isDark ? theme.colors.dark[7] : 'white'} fillOpacity={1} isAnimationActive={false} />
                        <Area yAxisId="left" type="monotone" dataKey="p10" stroke="none" fill={isDark ? theme.colors.dark[7] : 'white'} fillOpacity={1} isAnimationActive={false} />
                        <Line yAxisId="left" type="monotone" dataKey="p50" stroke={tealColor} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </Box>
                );
              })()}
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
                  Inserisci spesa netta annua e orizzonte per costruire una timeline di decumulo fiscale.
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
                          <Badge color={yearRiskPct(year) >= 50 ? 'red' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'yellow' : 'teal')} variant="light">
                            {yearRiskPct(year) >= 50 ? (floorEnabled ? 'Sotto soglia' : 'Rischio alto') : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'Anno critico' : 'Sostenibile')}
                          </Badge>
                        </Group>
                        <SimpleGrid cols={3} spacing="sm">
                          <ScenarioMetric label="Netto disp." value={formatMoney(year.net_spending_after_tax, currency)} />
                          <ScenarioMetric label="Tasse" value={formatMoney(year.estimated_taxes, currency)} />
                          <ScenarioMetric label="P50 Finale" value={formatMoney(year.p50_ending_capital, currency)} />
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
                      <Table.Th>Target netto</Table.Th>
                      <Table.Th>Lordo portafoglio</Table.Th>
                      <Table.Th>Tasse stimate</Table.Th>
                      <Table.Th>Netto totale</Table.Th>
                      <Table.Th>WR mediano</Table.Th>
                      <Table.Th>Capitale finale P50</Table.Th>
                      {floorEnabled && <Table.Th>Soglia</Table.Th>}
                      <Table.Th>Esito</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {decumulationPlan.map((year) => (
                      <Table.Tr key={year.year}>
                        <Table.Td>{year.year}</Table.Td>
                        <Table.Td>{year.age ?? 'N/D'}</Table.Td>
                        <Table.Td>{formatMoney(year.target_net_spending, currency)}</Table.Td>
                        <Table.Td>{formatMoney(year.gross_withdrawal, currency)}</Table.Td>
                        <Table.Td>{formatMoney(year.estimated_taxes, currency)}</Table.Td>
                        <Table.Td>{formatMoney(year.net_spending_after_tax, currency)}</Table.Td>
                        <Table.Td>{formatPct(year.p50_effective_withdrawal_rate_pct, 2)}</Table.Td>
                        <Table.Td>{formatMoney(year.p50_ending_capital, currency)}</Table.Td>
                        {floorEnabled && <Table.Td>{formatMoney(year.capital_floor, currency)}</Table.Td>}
                        <Table.Td>
                          <MantineTooltip
                            label={getDecumulationOutcomeTooltip(
                              floorEnabled ? year.floor_breach_probability_pct : year.depletion_probability_pct,
                              year.p50_effective_withdrawal_rate_pct,
                              swrValue,
                              floorEnabled,
                            )}
                            withArrow
                            multiline
                            maw={280}
                          >
                            <Badge color={yearRiskPct(year) >= 50 ? 'red' : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'yellow' : 'teal')} variant="light">
                              {yearRiskPct(year) >= 50 ? (floorEnabled ? 'Sotto soglia' : 'Fragile') : (year.p50_effective_withdrawal_rate_pct >= swrValue ? 'Critico' : 'OK')}
                            </Badge>
                          </MantineTooltip>
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
      <Modal
        opened={aggregateSelectionOpened}
        onClose={() => setAggregateSelectionOpened(false)}
        title="Perimetro FIRE aggregato"
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
        centered={!isMobile}
        styles={{
          body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
        }}
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
            bottom: isMobile ? 'calc(92px + var(--safe-area-bottom-floating))' : 24,
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
        pageContext="fire"
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

function OneOffExpensesEditor({
  expenses,
  onChange,
  currentAge,
}: {
  expenses: FireOneOffExpense[];
  onChange: (expenses: FireOneOffExpense[]) => void;
  currentAge: number | null;
}) {
  const updateExpense = (index: number, patch: Partial<FireOneOffExpense>) => {
    onChange(expenses.map((expense, i) => (i === index ? { ...expense, ...patch } : expense)));
  };

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <div>
          <Text fw={600} size="sm">Spese una tantum</Text>
          <Text size="xs" c="dimmed">
            {currentAge != null
              ? 'Uscite straordinarie in euro di oggi, all\'età indicata (auto, casa, studi).'
              : "Inserisci l'età attuale per collocare le spese nel tempo."}
          </Text>
        </div>
        <Button
          variant="light"
          size="xs"
          leftSection={<IconPlus size={14} />}
          onClick={() => onChange([...expenses, { age: (currentAge ?? 50) + 1, amount: 0, label: '' }])}
          disabled={expenses.length >= 50}
        >
          Aggiungi
        </Button>
      </Group>
      {expenses.map((expense, index) => (
        <Group key={index} gap="xs" align="flex-end" wrap="nowrap">
          <NumberInput
            label={index === 0 ? 'Età' : undefined}
            aria-label="Età spesa una tantum"
            value={expense.age}
            onChange={(value) => updateExpense(index, { age: Number(value) || 0 })}
            min={18}
            max={120}
            allowDecimal={false}
            w={80}
          />
          <NumberInput
            label={index === 0 ? 'Importo' : undefined}
            aria-label="Importo spesa una tantum"
            value={expense.amount}
            onChange={(value) => updateExpense(index, { amount: Number(value) || 0 })}
            min={0}
            thousandSeparator="."
            decimalSeparator=","
            style={{ flex: 1 }}
          />
          <TextInput
            label={index === 0 ? 'Descrizione' : undefined}
            aria-label="Descrizione spesa una tantum"
            value={expense.label}
            onChange={(event) => updateExpense(index, { label: event.currentTarget.value.slice(0, 80) })}
            placeholder="es. Auto"
            style={{ flex: 1 }}
          />
          <ActionIcon
            variant="subtle"
            color="red"
            size="lg"
            aria-label="Rimuovi spesa una tantum"
            onClick={() => onChange(expenses.filter((_, i) => i !== index))}
          >
            <IconTrash size={16} />
          </ActionIcon>
        </Group>
      ))}
    </Stack>
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
