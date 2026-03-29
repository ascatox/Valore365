import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InstantPortfolioAnalyzerPage } from './InstantPortfolioAnalyzerPage';
import { ApiRequestError } from '../services/api';

const analyzeInstantPortfolioMock = vi.fn();
const explainInstantInsightMock = vi.fn();

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  return {
    ...actual,
    analyzeInstantPortfolio: (...args: unknown[]) => analyzeInstantPortfolioMock(...args),
    explainInstantInsight: (...args: unknown[]) => explainInstantInsightMock(...args),
  };
});

function renderPage() {
  return render(
    <MantineProvider>
      <InstantPortfolioAnalyzerPage />
    </MantineProvider>,
  );
}

describe('InstantPortfolioAnalyzerPage', () => {
  beforeEach(() => {
    analyzeInstantPortfolioMock.mockReset();
    explainInstantInsightMock.mockReset();
  });

  it('renders analysis results after a successful submission', async () => {
    analyzeInstantPortfolioMock.mockResolvedValue({
      summary: {
        total_value: 17000,
        score: 74,
        risk_level: 'medium',
        diversification: 'good',
        overlap: 'moderate',
        cost_efficiency: 'low_cost',
      },
      positions: [
        {
          identifier: 'VWCE',
          resolved_symbol: 'VWCE',
          resolved_name: 'Vanguard FTSE All-World UCITS ETF',
          value: 10000,
          weight: 58.82,
          status: 'resolved',
        },
      ],
      unresolved: [],
      parse_errors: [],
      metrics: {
        geographic_exposure: {
          usa: 68,
          europe: 17,
          emerging: 10,
          other: 5,
        },
        asset_allocation: {
          Equity: 82.4,
          Bond: 17.6,
        },
        max_position_weight: 58.82,
        overlap_score: 61,
        portfolio_volatility: 14.8,
        weighted_ter: 0.21,
        risk_score: 4.47,
        estimated_drawdown: 30.6,
      },
      category_scores: {
        diversification: 18,
        risk: 18,
        concentration: 8,
        overlap: 10,
        cost_efficiency: 12,
      },
      alerts: [
        {
          severity: 'warning',
          code: 'HIGH_US_EXPOSURE',
          message: 'Your portfolio is heavily exposed to US markets (68%).',
        },
      ],
      suggestions: [
        {
          code: 'ADD_DIVERSIFICATION',
          message: 'Consider increasing exposure to non-US markets.',
        },
      ],
      insights: [
        {
          id: 'geo_usa',
          type: 'geo_concentration',
          severity: 'medium',
          score: 12,
          title: 'Sei molto concentrato su USA',
          short_description: 'Il 68.0% del tuo portafoglio dipende da quest\'area.',
          explanation_data: { region: 'USA', weight: 0.68 },
          cta_label: 'Spiegamelo meglio',
        },
      ],
      cta: {
        show_signup: true,
        message: 'Crea un account gratuito per salvare e monitorare questo portafoglio nel tempo.',
      },
    });
    explainInstantInsightMock.mockResolvedValue({
      insight_id: 'geo_usa',
      explanation: 'Questo significa che una parte ampia del portafoglio dipende dagli Stati Uniti.',
      source: 'template',
    });

    renderPage();

    expect(screen.getAllByAltText('Valore365').length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: /analizza portafoglio/i }));

    expect(await screen.findByText('74/100')).toBeInTheDocument();
    expect(screen.getAllByText('18 / 25')).toHaveLength(2);
    expect(screen.getByText('Vanguard FTSE All-World UCITS ETF')).toBeInTheDocument();
    expect(screen.getByText('Sei molto concentrato su USA')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /crea account gratis/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /spiegamelo meglio/i }));

    expect(await screen.findByText('Questo significa che una parte ampia del portafoglio dipende dagli Stati Uniti.')).toBeInTheDocument();
  }, 10000);

  it('hides the signup CTA when the response disables it', async () => {
    analyzeInstantPortfolioMock.mockResolvedValue({
      summary: {
        total_value: 17000,
        score: 74,
        risk_level: 'medium',
        diversification: 'good',
        overlap: 'moderate',
        cost_efficiency: 'low_cost',
      },
      positions: [
        {
          identifier: 'VWCE',
          resolved_symbol: 'VWCE',
          resolved_name: 'Vanguard FTSE All-World UCITS ETF',
          value: 10000,
          weight: 58.82,
          status: 'resolved',
        },
      ],
      unresolved: [],
      parse_errors: [],
      metrics: {
        geographic_exposure: {
          usa: 68,
          europe: 17,
          emerging: 10,
          other: 5,
        },
        asset_allocation: {
          Equity: 82.4,
          Bond: 17.6,
        },
        max_position_weight: 58.82,
        overlap_score: 61,
        portfolio_volatility: 14.8,
        weighted_ter: 0.21,
        risk_score: 4.47,
        estimated_drawdown: 30.6,
      },
      category_scores: {
        diversification: 18,
        risk: 18,
        concentration: 8,
        overlap: 10,
        cost_efficiency: 12,
      },
      alerts: [],
      suggestions: [],
      insights: [],
      cta: {
        show_signup: false,
        message: 'Crea un account gratuito per salvare e monitorare questo portafoglio nel tempo.',
      },
    });

    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /analizza portafoglio/i }));

    expect(await screen.findByText('74/100')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /crea account gratis/i })).not.toBeInTheDocument();
  }, 10000);

  it('shows parse and unresolved issues from API error details', async () => {
    analyzeInstantPortfolioMock.mockRejectedValue(
      new ApiRequestError({
        message: 'No valid positions found',
        code: 'bad_request',
        status: 400,
        details: {
          parse_errors: [
            {
              line: 1,
              raw: 'BAD',
              error: 'Expected format: IDENTIFIER VALUE',
            },
          ],
          unresolved: [
            {
              identifier: 'UNKNOWN',
              raw: 'UNKNOWN 1000',
              line: 2,
              error: 'Asset not found in the supported catalog',
            },
          ],
        },
      }),
    );

    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /analizza portafoglio/i }));

    expect(await screen.findByText('No valid positions found')).toBeInTheDocument();
    expect(screen.getByText('Riga 1: Expected format: IDENTIFIER VALUE')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN: Asset not found in the supported catalog')).toBeInTheDocument();
  }, 10000);
});
