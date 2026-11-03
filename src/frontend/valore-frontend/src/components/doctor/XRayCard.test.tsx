import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { XRayResponse } from '../../services/api';
import { XRayCard } from './XRayCard';
import { exposureRows, formatIsoDateIt, lookthroughCoverageText } from './xrayFormat';

let response: XRayResponse;

vi.mock('../dashboard/hooks/queries', () => ({
  usePortfolioXray: () => ({ data: response, isLoading: false, error: null }),
}));

vi.mock('../dashboard/holdings/AssetInfoModal', () => ({
  AssetInfoModal: () => null,
}));

function renderCard() {
  render(
    <MantineProvider>
      <XRayCard scope={1} />
    </MantineProvider>,
  );
}

describe('XRayCard', () => {
  beforeEach(() => {
    response = {
      portfolio_id: 1,
      aggregated_holdings: [],
      etf_details: [
        {
          symbol: 'WRLD',
          name: 'World Equity ETF',
          portfolio_weight_pct: 50,
          holdings_available: true,
          holdings_source: 'justetf',
          failure_reason: null,
          top_holdings: [],
          lookthrough_kind: 'fund',
          listed_holdings_pct: 45,
          data_source: 'justetf',
          data_as_of: '2026-09-30',
          data_as_of_basis: 'holdings_date',
        },
      ],
      etf_count: 1,
      coverage_pct: 50,
      lookthrough_coverage_pct: 62,
      funds_with_holdings_pct: 50,
      classified_country_pct: 40,
      classified_sector_pct: 30,
      coverage_denominator: 'Valore di mercato delle posizioni, liquidità esclusa',
      coverage_note: 'Scomposto il 62% del portafoglio',
      data_as_of: '2026-09-30',
      aggregated_country_exposure: { 'United States': 40, 'Non classificato': 60 },
      aggregated_sector_exposure: { Technology: 30, 'Non classificato': 70 },
      coverage_issues: [],
    };
  });

  it('shows the look-through coverage, the data date and the unclassified share', () => {
    renderCard();

    expect(screen.getByText('Scomposto il 62% del portafoglio')).toBeInTheDocument();
    expect(screen.getByText(/Dati del provider al 30\/09\/2026/)).toBeInTheDocument();
    expect(screen.getAllByText('Non classificato')).toHaveLength(2);
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.getByText('justETF al 30/09/2026')).toBeInTheDocument();
    expect(screen.getByText('Top holdings: 45% del fondo')).toBeInTheDocument();
  });

  it('falls back to the legacy coverage badge for an older response', () => {
    delete response.lookthrough_coverage_pct;
    renderCard();

    expect(screen.getByText('Copertura 50%')).toBeInTheDocument();
  });
});

describe('xrayFormat', () => {
  it('formats coverage and dates in Italian', () => {
    expect(lookthroughCoverageText(22.5)).toBe('Scomposto il 22,5% del portafoglio');
    expect(formatIsoDateIt('2026-09-30')).toBe('30/09/2026');
  });

  it('groups the rest and keeps the unclassified share last so rows sum to 100', () => {
    const dist: Record<string, number> = { 'Non classificato': 10 };
    for (let i = 0; i < 10; i += 1) dist[`C${i}`] = 9;
    const rows = exposureRows(dist, 8);

    expect(rows.map(([k]) => k).slice(-2)).toEqual(['Altri', 'Non classificato']);
    expect(rows.reduce((sum, [, v]) => sum + v, 0)).toBeCloseTo(100, 5);
  });
});
