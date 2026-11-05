import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import type { DoctorMetricValue, DoctorScenarioResult, DoctorScenarioSide } from '../../../services/api/types';
import { stubLayoutApis } from '../../../test/pageHarness';
import { ScenarioComparisonTable } from './ScenarioComparisonTable';
import { ScenarioFeasibilitySummary } from './ScenarioFeasibilitySummary';
import { ScenarioTradeoffs } from './ScenarioTradeoffs';

const metric = (code: string, value: number | null, quality: DoctorMetricValue['quality'] = 'ok'): DoctorMetricValue => ({
  code, value, lower: null, upper: null, unit: 'pct', coverage_pct: value == null ? 40 : 100, quality,
});

const VOLATILITY_REASON = 'Volatilità dopo lo scenario non stimabile: servono serie storiche';

const side = (single: number, usa: number | null, failed: number): DoctorScenarioSide => ({
  invested_value: 125000,
  cash_value: 0,
  total_value: 125000,
  evaluation_status: 'ready',
  rule_results: [],
  volatility: { value: null, status: 'not_available', reason: VOLATILITY_REASON },
  metrics: {
    max_single_position_pct: metric('max_single_position_pct', single),
    usa_exposure_pct: metric('usa_exposure_pct', usa, usa == null ? 'partial' : 'ok'),
    weighted_ter_pct: metric('weighted_ter_pct', 0.22),
  },
  evaluation_summary: { passed: 4 - failed, failed, unknown: 1, not_applicable: 0, inactive: 0, near_limit: 0, total: 5 },
});

const result = (overrides: Partial<DoctorScenarioResult> = {}): DoctorScenarioResult => ({
  label: 'Scenario A',
  mode: 'new_cash_only',
  feasible: true,
  infeasible_code: null,
  infeasible_reason: null,
  scope: { portfolio_ids: [1], scope_type: 'single', fingerprint: 'p:1' },
  policy_id: 7,
  policy_version: 3,
  before: side(46.6, 60, 1),
  after: side(34.9, null, 0),
  changes: [{
    asset_id: 1, symbol: 'VWRA', name: 'Vanguard FTSE All-World', isin: 'IE00BK5BQT80', asset_class: 'equity', action: 'hold',
    before_value: 58250, after_value: 58250, delta_value: 0, before_weight: 46.6, after_weight: 34.9, delta_weight: -11.7, fees: 0,
  }],
  warnings: ['Volatilità dopo lo scenario: N/D (non stimabile)'],
  violations_resolved: [{
    rule_id: 'max-single', metric_code: 'max_single_position_pct', label: 'Max singolo ETF', reason: null,
    before_status: 'FAIL', after_status: 'PASS', before_actual: 46.6, after_actual: 34.9,
  }],
  violations_new: [],
  required_new_cash: 41000,
  total_before: 125000,
  total_after: 166000,
  cash_in: 41000,
  costs: { total: 12.5, variable: 10.5, fixed: 2, operations: 1, fee_model: { pct: 0.1, fixed: 2 } },
  turnover_pct: 0,
  methodology_version: 'doctor-policy-1.0',
  snapshot_id: 'abc123',
  data_quality: null,
  calculated_at: '2026-11-05T10:00:00Z',
  tax_model: 'none',
  disclaimer: 'Simulazione teorica; nessun ordine eseguito.',
  ...overrides,
});

const wrap = (ui: ReactNode) => render(<MantineProvider>{ui}</MantineProvider>);

beforeEach(() => {
  window.localStorage.clear();
  stubLayoutApis();
});

describe('ScenarioComparisonTable', () => {
  it('renders Attuale vs scenarios as a table on desktop, with improvements and incomplete data marked', () => {
    const b = result({ label: 'Scenario B', after: side(50, 62, 2), violations_resolved: [], violations_new: ['max-single'] });
    wrap(
      <ScenarioComparisonTable
        current={result().before}
        scenarios={[result(), b]}
        isMobile={false}
        ruleMetric={new Map([['max-single', 'max_single_position_pct']])}
      />,
    );
    const table = screen.getByTestId('scenario-comparison-table');
    expect(within(table).getByRole('columnheader', { name: 'Attuale' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Scenario A' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Scenario B' })).toBeInTheDocument();
    const singleRow = within(table).getByRole('rowheader', { name: /Peso massimo singola posizione/ }).closest('tr')!;
    expect(within(singleRow).getByText('46,6%')).toBeInTheDocument();
    expect(within(singleRow).getByText('34,9%')).toBeInTheDocument();
    expect(within(singleRow).getByText('Migliora')).toBeInTheDocument();
    expect(within(singleRow).getByText('Peggiora')).toBeInTheDocument();
    const usaRow = within(table).getByRole('rowheader', { name: /Esposizione USA/ }).closest('tr')!;
    expect(within(usaRow).getByText('N/D')).toBeInTheDocument();
    expect(within(usaRow).getByText('Dati incompleti')).toBeInTheDocument();
    const complianceRow = within(table).getByRole('rowheader', { name: /Conformità/ }).closest('tr')!;
    expect(within(complianceRow).getByText('4 rispettati · 0 violati · 1 non verificabile')).toBeInTheDocument();
    expect(screen.queryByTestId('scenario-comparison-cards')).not.toBeInTheDocument();
  });

  it('becomes stacked cards on mobile (no wide table)', () => {
    wrap(<ScenarioComparisonTable current={result().before} scenarios={[result()]} isMobile />);
    expect(screen.getByTestId('scenario-comparison-cards')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('Attuale: 46,6%')).toBeInTheDocument();
  });
});

describe('ScenarioFeasibilitySummary', () => {
  it('shows the infeasible reason from the backend', () => {
    wrap(
      <ScenarioFeasibilitySummary
        result={result({ feasible: false, infeasible_reason: 'Con il vincolo «nessuna vendita» servono almeno 41.000 € di nuova liquidità', after: null })}
        currency="EUR"
        privacy={false}
      />,
    );
    expect(screen.getByText('Scenario A: non fattibile')).toBeInTheDocument();
    expect(screen.getByText(/servono almeno 41\.000 € di nuova liquidità/)).toBeInTheDocument();
  });

  it('masks € amounts in Privacy Mode', () => {
    wrap(<ScenarioFeasibilitySummary result={result()} currency="EUR" privacy />);
    expect(screen.getByTestId('required-new-cash')).toHaveTextContent('******');
    expect(screen.queryByText(/41\.000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/125\.000/)).not.toBeInTheDocument();
  });

  it('shows the infeasible scenario as N/D in the comparison', () => {
    wrap(<ScenarioComparisonTable current={result().before} scenarios={[result({ feasible: false, after: null })]} isMobile={false} />);
    expect(screen.getAllByText('Dati incompleti').length).toBeGreaterThan(0);
  });
});

describe('ScenarioTradeoffs', () => {
  it('lists resolved rules, warnings and weights only (no per-account orders) in aggregate', () => {
    wrap(<ScenarioTradeoffs result={result()} currency="EUR" privacy={false} isAggregate isMobile={false} />);
    expect(screen.getByText('✓ Max singolo ETF')).toBeInTheDocument();
    expect(screen.getByText('Volatilità dopo lo scenario: N/D (non stimabile)')).toBeInTheDocument();
    expect(screen.getByText('Pesi complessivi (nessun ordine per singolo conto)')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Variazione' })).not.toBeInTheDocument();
  });
});

describe('Lab review fixes', () => {
  it('masks € amounts in the infeasible reason in Privacy Mode (percentages stay)', () => {
    wrap(
      <ScenarioFeasibilitySummary
        result={result({ feasible: false, infeasible_reason: 'Servono almeno 227.029 € di nuova liquidità per portare VWRA al 35%', after: null })}
        currency="EUR"
        privacy
      />,
    );
    expect(screen.getByText('Servono almeno ****** di nuova liquidità per portare VWRA al 35%')).toBeInTheDocument();
    expect(screen.queryByText(/227\.029/)).not.toBeInTheDocument();
  });

  it('masks € amounts in warnings and rule reasons of the tradeoffs in Privacy Mode', () => {
    const value = result({
      warnings: ['Liquidità residua 10.000 € non investita', 'Turnover 12,5%'],
      violations_new: [{ rule_id: 'ter', metric_code: 'weighted_ter_pct', label: 'TER', reason: 'Costo annuo stimato 250 €', before_status: 'PASS', after_status: 'FAIL' }],
    });
    wrap(<ScenarioTradeoffs result={value} currency="EUR" privacy isAggregate={false} isMobile={false} />);
    expect(screen.getByText('Liquidità residua ****** non investita')).toBeInTheDocument();
    expect(screen.getByText('Turnover 12,5%')).toBeInTheDocument();
    expect(screen.getByText('✗ TER: Costo annuo stimato ******')).toBeInTheDocument();
    expect(screen.queryByText(/10\.000|250 €/)).not.toBeInTheDocument();
  });

  it('shows the warnings unmasked outside Privacy Mode', () => {
    wrap(<ScenarioTradeoffs result={result({ warnings: ['Liquidità residua 10.000 € non investita'] })} currency="EUR" privacy={false} isAggregate isMobile={false} />);
    expect(screen.getByText('Liquidità residua 10.000 € non investita')).toBeInTheDocument();
  });

  it('shows costs.total as the hypothetical cost, and N/D only when it is null', () => {
    const { unmount } = wrap(<ScenarioFeasibilitySummary result={result()} currency="EUR" privacy={false} />);
    const costs = screen.getByText('Costi ipotetici').nextElementSibling!;
    expect(costs.textContent).toMatch(/12,50\s?€/);
    unmount();
    wrap(<ScenarioFeasibilitySummary result={result({ costs: { total: 0, variable: 0, fixed: 0, operations: 0, fee_model: null } })} currency="EUR" privacy={false} />);
    expect(screen.getByText('Costi ipotetici').nextElementSibling!.textContent).toMatch(/0,00\s?€/);
  });

  it('shows N/D for costs when the backend total is null', () => {
    wrap(<ScenarioFeasibilitySummary result={result({ costs: { total: null, variable: null, fixed: null, operations: 0, fee_model: null } })} currency="EUR" privacy={false} />);
    expect(screen.getByText('Costi ipotetici').nextElementSibling).toHaveTextContent('N/D');
  });

  it('shows a «Volatilità» row with N/D and the backend reason in the desktop table', () => {
    wrap(<ScenarioComparisonTable current={result().before} scenarios={[result()]} isMobile={false} />);
    const table = screen.getByTestId('scenario-comparison-table');
    const row = within(table).getByRole('rowheader', { name: /Volatilità/ }).closest('tr')!;
    expect(within(row).getAllByText('N/D')).toHaveLength(2);
    expect(within(row).getAllByText(VOLATILITY_REASON)).toHaveLength(2);
  });

  it('shows the «Volatilità» line with N/D and the reason in the mobile cards', () => {
    wrap(<ScenarioComparisonTable current={result().before} scenarios={[result()]} isMobile />);
    const cards = screen.getByTestId('scenario-comparison-cards');
    expect(within(cards).getByText('Rischio · Volatilità')).toBeInTheDocument();
    const line = within(cards).getByText('Rischio · Volatilità').parentElement!;
    expect(within(line).getByText('Attuale: N/D')).toBeInTheDocument();
    expect(within(line).getByText(VOLATILITY_REASON)).toBeInTheDocument();
  });
});
