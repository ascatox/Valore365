import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import type { StressTestResponse, StressTestScenarioResult } from '../../services/api';
import { StressTestCard } from './StressTestCard';

const NOTE =
  "Stima basata su indici di riferimento in dollari (USD) per asset class: non include l'effetto del cambio EUR/USD, che può cambiare in modo rilevante il risultato per un investitore in euro.";

let response: StressTestResponse;

// SegmentedControl measures itself; jsdom has no ResizeObserver.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

vi.mock('../dashboard/hooks/queries', () => ({
  useStressTest: () => ({ data: response, isLoading: false, error: null }),
}));

const scenario = (overrides: Partial<StressTestScenarioResult>): StressTestScenarioResult => ({
  scenario_id: 'gfc_2008',
  scenario_name: 'Crisi 2008',
  scenario_type: 'historical',
  period: '2007-2009',
  estimated_portfolio_impact_pct: -30,
  max_drawdown_pct: -32,
  recovery_months: 12,
  benchmark_drawdown_pct: -55,
  risk_level: 'critical',
  most_impacted_assets: [],
  ...overrides,
});

function renderCard(scenarios: StressTestScenarioResult[]) {
  response = { portfolio_id: 1, scenarios, portfolio_volatility_pct: null, analysis_date: '2026-11-02' };
  render(
    <MantineProvider>
      <StressTestCard scope={1} />
    </MantineProvider>,
  );
}

describe('StressTestCard', () => {
  it('shows the method badge with coverage and the USD/FX note for proxy estimates', () => {
    renderCard([
      scenario({ method: 'proxy', coverage_pct: 30, methodology_note: NOTE }),
      scenario({ scenario_id: 'covid_crash', scenario_name: 'Covid', method: 'historical', coverage_pct: 100 }),
    ]);

    expect(screen.getByText('Stima per asset class · copertura 30%')).toBeInTheDocument();
    expect(screen.getByText('Storico · copertura 100%')).toBeInTheDocument();
    expect(screen.getByText('Limite della stima storica')).toBeInTheDocument();
    expect(screen.getByText(NOTE)).toBeInTheDocument();
  });

  it('hides the note when every historical scenario uses real prices', () => {
    renderCard([scenario({ method: 'historical', coverage_pct: 100, methodology_note: null })]);

    expect(screen.getByText('Storico · copertura 100%')).toBeInTheDocument();
    expect(screen.queryByText('Limite della stima storica')).not.toBeInTheDocument();
  });
});
