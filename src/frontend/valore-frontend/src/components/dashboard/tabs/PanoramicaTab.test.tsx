import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../constants';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis, summary } from '../../../test/pageHarness';
import { PanoramicaTab } from './PanoramicaTab';

const PORTFOLIOS = [portfolio(1, 'Core')];
const LOSS_DAY = summary(1, {
  market_value: 650000,
  unrealized_pl: 101665.32,
  unrealized_pl_pct: 18.59,
  day_change: -13333.27,
  day_change_pct: -2.01,
  cash_balance: 4321,
});

function renderTab(summaryBody: unknown = LOSS_DAY) {
  storeScope({ mode: 'single', id: 1 });
  installFetchMock(PORTFOLIOS, (request) => (request.path === '/portfolios/1/summary' ? summaryBody : undefined));
  return renderWithApp(<PanoramicaTab scope={{ mode: 'single', id: 1 }} chartWindow="90" setChartWindow={() => {}} />);
}

/** The KPI card whose label is `label` (labels are unique). */
const card = (label: string) => screen.getByText(label, { exact: true }).closest('.mantine-Paper-root') as HTMLElement;

function setMobile(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matches && query.includes('max-width: 48em'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

describe('PanoramicaTab KPI row', () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  it('splits the daily variation into an amount card and a percentage card, with no cash card', async () => {
    renderTab();
    await waitFor(() => expect(within(card('Var. Giornaliera')).getByText('-13.333,27 €')).toBeInTheDocument());

    const labels = Array.from(document.querySelectorAll('.mantine-SimpleGrid-root > .mantine-Paper-root'))
      .map((el) => el.querySelector('p')?.textContent);
    expect(labels).toEqual(['Var. Giornaliera\u00A0%', 'Var. Giornaliera', 'Valore Totale', 'P/L Totale', 'P/L %']);

    // The amount card shows only money; the percentage lives in its own card.
    expect(card('Var. Giornaliera')).not.toHaveTextContent('%');
    expect(within(card('Var. Giornaliera %')).getByText('-2,01%')).toBeInTheDocument();
    expect(within(card('P/L Totale')).getByText('+101.665,32 €')).toBeInTheDocument();
    expect(within(card('P/L %')).getByText('+18,59%')).toBeInTheDocument();

    expect(screen.queryByText('Cash')).not.toBeInTheDocument();
    expect(screen.queryByText('4.321,00 €')).not.toBeInTheDocument();
  });

  it('colours the daily cards by sign and points the percentage arrow down on a loss', async () => {
    renderTab();
    const amount = await within(card('Var. Giornaliera')).findByText('-13.333,27 €');
    const pct = within(card('Var. Giornaliera %')).getByText('-2,01%');
    expect(amount.style.color).toContain('red');
    expect(pct.style.color).toContain('red');
    expect(card('Var. Giornaliera %').querySelector('.tabler-icon-arrow-down-right')).not.toBeNull();
    // A gain on P/L keeps the up arrow.
    expect(card('P/L %').querySelector('.tabler-icon-arrow-up-right')).not.toBeNull();
  });

  it('masks the amount in privacy mode and keeps the percentage, like the P/L pair', async () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    renderTab();
    expect(await within(card('Var. Giornaliera %')).findByText('-2,01%')).toBeInTheDocument();
    expect(within(card('Var. Giornaliera')).getByText('******')).toBeInTheDocument();
    expect(within(card('P/L Totale')).getByText('******')).toBeInTheDocument();
    expect(within(card('P/L %')).getByText('+18,59%')).toBeInTheDocument();
  });

  it('shows N/D on both daily cards while the summary is missing', () => {
    storeScope({ mode: 'single', id: 1 });
    installFetchMock(PORTFOLIOS, (request) => (request.path === '/portfolios/1/summary' ? PENDING : undefined));
    renderWithApp(<PanoramicaTab scope={{ mode: 'single', id: 1 }} chartWindow="90" setChartWindow={() => {}} />);
    expect(within(card('Var. Giornaliera')).getByText('N/D')).toBeInTheDocument();
    expect(within(card('Var. Giornaliera %')).getByText('N/D')).toBeInTheDocument();
  });

  it('on mobile shows today\'s amount in the hero and the percentage first in the carousel, in place of cash', async () => {
    setMobile(true);
    renderTab();
    expect(await screen.findByText('-13.333,27 €')).toBeInTheDocument();
    // The hero badge no longer appends the percentage to the amount.
    expect(screen.queryByText(/-13\.333,27 € \(/)).not.toBeInTheDocument();
    const pctLabel = screen.getByText('Var. giorn. %');
    expect(pctLabel.parentElement?.parentElement?.firstElementChild).toBe(pctLabel.parentElement);
    expect(pctLabel.parentElement).toHaveTextContent('-2,01%');
    expect(screen.queryByText('Liquidità')).not.toBeInTheDocument();
    expect(screen.queryByText('4.321,00 €')).not.toBeInTheDocument();
    expect(screen.getByText('Valore titoli')).toBeInTheDocument();
    expect(screen.getByText('Investito')).toBeInTheDocument();
  });
});
