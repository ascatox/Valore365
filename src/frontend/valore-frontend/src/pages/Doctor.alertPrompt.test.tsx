import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { DoctorPage } from './Doctor.page';

const health: PortfolioHealthResponse = {
  portfolio_id: 1,
  portfolio_ids: null,
  score: 64,
  summary: { risk_level: 'medium', diversification: 'good', overlap: 'high', cost_efficiency: 'low_cost' },
  metrics: {
    geographic_exposure: { usa: 60, europe: 30, emerging: 10 },
    sector_exposure: {},
    max_position_weight: 30,
    overlap_score: 42,
    portfolio_volatility: 12,
    weighted_ter: 0.2,
  },
  category_scores: { diversification: 15, risk: 15, concentration: 15, overlap: 5, cost_efficiency: 12 },
  alerts: [{
    severity: 'warning',
    type: 'etf_overlap',
    message: 'Alcuni ETF si sovrappongono molto',
    details: null,
    education: {
      code: 'etf_overlap',
      title: 'Sovrapposizione',
      what_it_means: 'Gli ETF contengono gli stessi titoli.',
      why_it_matters: 'La diversificazione reale è minore.',
      how_to_read_it: 'Guarda le coppie con overlap alto.',
      concept: 'Sovrapposizione tra ETF',
      copilot_prompts: ['Quali ETF si sovrappongono di più?'],
    },
  }],
  suggestions: [],
};

describe('Doctor alert details → Copilot prompt', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    storeScope({ mode: 'single', id: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the selected prompt with the alert context and records the alert type', async () => {
    installFetchMock([portfolio(1, 'Core')], (request) => {
      if (request.path === '/copilot/status') return { available: true };
      if (/\/health(\?|$)/.test(request.path)) return health;
      if (/\/(xray|monte-carlo|stress-test)(\?|$)/.test(request.path)) return PENDING;
      if (request.path === '/copilot/chat') return new Response('', { status: 200 });
      return undefined;
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    renderWithApp(<DoctorPage />, { route: '/doctor' });

    fireEvent.click(await screen.findByRole('button', { name: 'Approfondisci' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Quali ETF si sovrappongono di più?' }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/copilot/chat'))).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/copilot/chat'))!;
    const body = JSON.parse(String((init as RequestInit).body));
    const sent = body.messages[body.messages.length - 1].content as string;
    expect(sent.startsWith('Quali ETF si sovrappongono di più?')).toBe(true);
    expect(sent).toContain('Contesto Doctor: alert "Alcuni ETF si sovrappongono molto" (etf_overlap).');
    expect(sent).toContain('Concetto chiave: Sovrapposizione tra ETF.');
    expect(sent).not.toContain('[object Object]');

    const stats = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.doctorEducationStats) ?? '{}');
    expect(stats.today.exploredAlertTypes).toEqual(['etf_overlap']);
    expect(stats.today.educationPromptClicks).toBe(1);
  });
});
