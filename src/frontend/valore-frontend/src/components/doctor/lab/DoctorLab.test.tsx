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

const side = (single: number, usa: number | null, failed: number): DoctorScenarioSide => ({
  metrics: {
    max_single_position_pct: metric('max_single_position_pct', single),
    usa_exposure_pct: metric('usa_exposure_pct', usa, usa == null ? 'partial' : 'ok'),
    weighted_ter_pct: metric('weighted_ter_pct', 0.22),
  },
  evaluation_summary: { passed: 4 - failed, failed, unknown: 1, not_applicable: 0, inactive: 0, near_limit: 0, total: 5 },
});

const result = (overrides: Partial<DoctorScenarioResult> = {}): DoctorScenarioResult => ({
  label: 'Scenario A',
  feasible: true,
  infeasible_reason: null,
  before: side(46.6, 60, 1),
  after: side(34.9, null, 0),
  changes: [{ asset_id: 1, symbol: 'VWRA', before_value: 58250, after_value: 58250, before_weight: 46.6, after_weight: 34.9, delta_value: 0 }],
  warnings: ['Volatilità dopo lo scenario: N/D (non stimabile)'],
  violations_resolved: [{ rule_id: 'max-single', metric_code: 'max_single_position_pct', label: 'Max singolo ETF' }],
  violations_new: [],
  required_new_cash: 41000,
  total_before: 125000,
  total_after: 166000,
  cash_in: 41000,
  costs: 0,
  methodology_version: 'doctor-policy-1.0',
  snapshot_id: 'abc123',
  data_quality: null,
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
