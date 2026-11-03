import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { XRayResponse } from '../../services/api';
import { XRayCard } from './XRayCard';
import {
  applicableCoverageText,
  exposureRows,
  formatIsoDateIt,
  lookthroughCoverageText,
  lookthroughStatusBadge,
} from './xrayFormat';

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

  it('separates not applicable positions from missing data (TASK-52)', () => {
    response.etf_details.push(
      {
        symbol: 'GLD',
        name: 'SPDR Gold Shares',
        portfolio_weight_pct: 20,
        holdings_available: false,
        holdings_source: 'missing',
        failure_reason: 'asset class gold: no underlying securities to look through',
        top_holdings: [],
        lookthrough_kind: 'no_lookthrough',
        lookthrough_status: 'not_applicable',
        lookthrough_reason: 'Oro: non ha titoli azionari sottostanti da scomporre.',
      },
      {
        symbol: 'VEUR',
        name: 'Vanguard FTSE Developed Europe UCITS ETF',
        portfolio_weight_pct: 30,
        holdings_available: false,
        holdings_source: 'missing',
        failure_reason: 'yfinance returned no top holdings',
        top_holdings: [],
        lookthrough_kind: 'missing',
        lookthrough_status: 'missing',
        lookthrough_reason: 'Dati mancanti: nessun arricchimento justETF salvato.',
      },
    );
    response.applicable_lookthrough_coverage_pct = 28.1;
    response.not_applicable_pct = 20;
    response.missing_pct = 30;
    response.coverage_issues = [
      { asset_id: 5, symbol: 'GLD', name: 'SPDR Gold Shares', reason: 'asset class gold', lookthrough_status: 'not_applicable' },
      { asset_id: 6, symbol: 'VEUR', name: 'VEUR', reason: 'yfinance returned no top holdings', lookthrough_status: 'missing' },
    ];
    renderCard();

    expect(
      screen.getByText('Scomposto il 28,1% della parte azionaria; 20% non applicabile (oro); 30% con dati mancanti'),
    ).toBeInTheDocument();
    expect(screen.getByText('non applicabile')).toBeInTheDocument();
    expect(screen.getByText('dati mancanti')).toBeInTheDocument();
    // Only the missing position is a coverage problem.
    expect(screen.getByText('Un ETF/fondo non ha holdings affidabili disponibili.')).toBeInTheDocument();
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

  it('describes the applicable coverage and the per-position status', () => {
    expect(
      applicableCoverageText({
        applicable_lookthrough_coverage_pct: 30,
        not_applicable_pct: 70,
        missing_pct: 0,
        etf_details: [
          { lookthrough_status: 'not_applicable', lookthrough_reason: 'Oro: non ha titoli.' },
          { lookthrough_status: 'not_applicable', lookthrough_reason: 'Obbligazioni: non modellato.' },
          { lookthrough_status: 'not_applicable', lookthrough_reason: 'Obbligazioni: non modellato.' },
        ],
      }),
    ).toBe('Scomposto il 30% della parte azionaria; 70% non applicabile (oro, obbligazioni)');
    expect(applicableCoverageText({ applicable_lookthrough_coverage_pct: null, not_applicable_pct: 100, missing_pct: 0, etf_details: [] }))
      .toBe('Look-through azionario non applicabile; 100% non applicabile');
    expect(applicableCoverageText({ etf_details: [] })).toBeNull();
    expect(lookthroughStatusBadge('not_applicable')).toEqual({ label: 'non applicabile', color: 'gray' });
    expect(lookthroughStatusBadge('missing')).toEqual({ label: 'dati mancanti', color: 'orange' });
    expect(lookthroughStatusBadge('available')).toBeNull();
    expect(lookthroughStatusBadge(undefined)).toBeNull();
  });

  it('groups the rest and keeps the unclassified share last so rows sum to 100', () => {
    const dist: Record<string, number> = { 'Non classificato': 10 };
    for (let i = 0; i < 10; i += 1) dist[`C${i}`] = 9;
    const rows = exposureRows(dist, 8);

    expect(rows.map(([k]) => k).slice(-2)).toEqual(['Altri', 'Non classificato']);
    expect(rows.reduce((sum, [, v]) => sum + v, 0)).toBeCloseTo(100, 5);
  });
});
