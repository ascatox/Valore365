import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { DoctorPage } from './Doctor.page';

const captured: { nodes: HTMLElement[] } = { nodes: [] };
vi.mock('html-to-image', () => ({
  toPng: vi.fn(async (node: HTMLElement) => { captured.nodes.push(node); return 'data:image/png;base64,AAAA'; }),
  toBlob: vi.fn(async (node: HTMLElement) => { captured.nodes.push(node); return new Blob(['x'], { type: 'image/png' }); }),
}));

const health: PortfolioHealthResponse = {
  portfolio_id: 1,
  portfolio_ids: null,
  score: 72,
  summary: { risk_level: 'medium', diversification: 'good', overlap: 'low', cost_efficiency: 'low_cost' },
  metrics: {
    geographic_exposure: { usa: 60, europe: 30, emerging: 10 },
    sector_exposure: {},
    max_position_weight: 46.6,
    overlap_score: 10,
    portfolio_volatility: 12,
    weighted_ter: 0.2,
  },
  category_scores: { diversification: 15, risk: 15, concentration: 15, overlap: 15, cost_efficiency: 12 },
  alerts: [],
  suggestions: [],
};

type Viewport = 'desktop' | 'tablet' | 'mobile';
const originalMatchMedia = window.matchMedia;

/** Answers Mantine's useMediaQuery for the given viewport. */
function mockViewport(viewport: Viewport) {
  const matches = (query: string) => {
    if (query.includes('max-width: 48em')) return viewport === 'mobile';
    if (query.includes('min-width: 75em')) return viewport === 'desktop';
    return false;
  };
  window.matchMedia = ((query: string) => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

function mockDoctorApi() {
  return installFetchMock([portfolio(1, 'Core')], (request) => {
    if (request.path === '/copilot/status') return { available: true };
    if (/\/health(\?|$)/.test(request.path)) return health;
    if (/\/(xray|monte-carlo|stress-test)(\?|$)/.test(request.path)) return PENDING;
    return undefined;
  });
}

async function openCopilot() {
  renderWithApp(<DoctorPage />, { route: '/doctor' });
  await screen.findByText('Dettaglio metriche');
  fireEvent.click(await screen.findByRole('button', { name: 'Apri Doctor Copilot' }));
}

describe('Doctor Copilot layout', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    storeScope({ mode: 'single', id: 1 });
    captured.nodes = [];
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  it('desktop: a ~380px side panel next to the content, no modal, closable', async () => {
    mockViewport('desktop');
    mockDoctorApi();
    await openCopilot();

    const panel = await screen.findByRole('complementary', { name: 'Doctor Copilot' });
    expect(panel.querySelector('[data-copilot-layout="side-panel"]')).not.toBeNull();
    expect(screen.getByTestId('doctor-copilot-panel')).toHaveStyle({ width: '380px' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // The page stays usable next to the panel.
    expect(screen.getByText('Dettaglio metriche')).toBeVisible();
    fireEvent.click(within(panel).getByRole('button', { name: 'Chiudi copilot' }));
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Doctor Copilot' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Apri Doctor Copilot' })).toBeInTheDocument();
  });

  it('tablet: a drawer', async () => {
    mockViewport('tablet');
    mockDoctorApi();
    await openCopilot();
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector('[data-copilot-layout="drawer"]')).not.toBeNull();
    expect(screen.queryByRole('complementary', { name: 'Doctor Copilot' })).not.toBeInTheDocument();
  });

  it('mobile: the BottomSheet', async () => {
    mockViewport('mobile');
    mockDoctorApi();
    await openCopilot();
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector('[data-copilot-layout="bottom-sheet"]')).not.toBeNull();
  });

  it('other pages keep the drawer by default', async () => {
    mockViewport('desktop');
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}')));
    render(
      <MantineProvider>
        <CopilotChat opened onClose={() => {}} portfolioId={1} pageContext="dashboard" />
      </MantineProvider>,
    );
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelector('[data-copilot-layout="drawer"]')).not.toBeNull();
  });
});

describe('Doctor share/export in Privacy Mode', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    storeScope({ mode: 'single', id: 1 });
    captured.nodes = [];
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  it('masks the score in the copied summary and in the exported image', async () => {
    mockViewport('desktop');
    mockDoctorApi();
    const writeText = vi.fn(async () => {});
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText }, userAgent: 'jsdom' });
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    await screen.findByText('Dettaglio metriche');

    fireEvent.click(screen.getByRole('button', { name: 'Condividi il referto' }));
    fireEvent.click(await screen.findByText('Copia riepilogo'));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const copied = String((writeText.mock.calls as unknown as string[][])[0][0]);
    expect(copied).toContain('Score: ******/100');
    expect(copied).not.toContain('72');

    fireEvent.click(screen.getByRole('button', { name: 'Condividi il referto' }));
    fireEvent.click(await screen.findByText('Condividi immagine'));
    await waitFor(() => expect(captured.nodes.length).toBeGreaterThan(0));
    const exported = captured.nodes[0].textContent ?? '';
    expect(exported).toContain('••');
    expect(exported).not.toContain('72');
    expect(exported).not.toMatch(/€/);
  });
});
