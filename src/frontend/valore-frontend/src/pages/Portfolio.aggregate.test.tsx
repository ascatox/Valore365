import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TransactionListItem } from '../services/api';
import { installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { PortfolioPage } from './Portfolio.page';

const PORTFOLIOS = [portfolio(1, 'Core'), portfolio(2, 'Pensione')];
const AGG = 'portfolio_ids=1&portfolio_ids=2';

const tx = (id: number, portfolio_id: number, portfolio_name: string, symbol: string): TransactionListItem => ({
  id,
  portfolio_id,
  portfolio_name,
  asset_id: 100 + id,
  symbol,
  asset_name: `${symbol} asset`,
  side: 'buy',
  trade_at: `2026-0${id}-01T10:00:00Z`,
  quantity: 2,
  price: 50,
  fees: 1,
  taxes: 0,
  trade_currency: 'EUR',
  notes: null,
});

const AGGREGATE_TRANSACTIONS = [tx(2, 2, 'Pensione', 'AGGH'), tx(1, 1, 'Core', 'VWCE')];

function renderAggregatePortfolio(route = '/portfolio') {
  storeScope({ mode: 'aggregate', ids: [1, 2] });
  const api = installFetchMock(PORTFOLIOS, (request) => (
    request.path === `/portfolios/aggregate/transactions?${AGG}` ? AGGREGATE_TRANSACTIONS : undefined
  ));
  const view = renderWithApp(<PortfolioPage />, { route });
  return { api, ...view };
}

describe('PortfolioPage in the aggregate view (read-only)', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists the merged transactions with a Portafoglio column', async () => {
    const { api } = renderAggregatePortfolio();

    const table = (await screen.findByRole('columnheader', { name: 'Portafoglio' })).closest('table')!;
    await within(table).findByText('VWCE');
    expect(within(table).getByText('Core')).toBeInTheDocument();
    expect(within(table).getByText('Pensione')).toBeInTheDocument();
    expect(api.paths()).toContain(`/portfolios/aggregate/transactions?${AGG}`);
    // Nothing per portfolio: no single transactions, no target allocation.
    expect(api.paths().some((path) => /^\/portfolios\/\d+\//.test(path))).toBe(false);
  });

  it('disables every write action with the reason and sends no write request', async () => {
    const { api } = renderAggregatePortfolio();
    await screen.findByText('VWCE', { selector: 'p' });

    const newTransaction = screen.getByRole('button', { name: 'Nuova Transazione' });
    const importButton = screen.getByRole('button', { name: 'Importa' });
    for (const button of [newTransaction, importButton]) {
      expect(button).toBeDisabled();
      expect(button.closest('[data-aggregate-read-only]')).not.toBeNull();
    }
    for (const button of [
      screen.getByRole('button', { name: 'Modifica transazione 1' }),
      screen.getByRole('button', { name: 'Elimina transazione 1' }),
    ]) {
      expect(button).toBeDisabled();
      fireEvent.click(button);
    }
    expect(screen.getByRole('button', { name: /Esporta per AI/ })).toBeDisabled();

    // The read-only reason is shown on hover.
    fireEvent.mouseEnter(newTransaction.closest('[data-aggregate-read-only]')!);
    expect(await screen.findByText('Seleziona un solo portafoglio per modificare')).toBeInTheDocument();

    fireEvent.click(newTransaction);
    fireEvent.click(importButton);
    expect(api.writes()).toEqual([]);
  });

  it('replaces the cash and PAC tabs with a notice', async () => {
    const { api } = renderAggregatePortfolio();
    await screen.findByText('VWCE', { selector: 'p' });

    fireEvent.click(screen.getByRole('tab', { name: /Liquidità/ }));
    expect(await screen.findByText(/liquidità e i suoi movimenti sono gestiti per singolo portafoglio/)).toBeInTheDocument();
    expect(screen.getAllByText('Non disponibile nella vista aggregata').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('tab', { name: /Piano di Accumulo/ }));
    expect(await screen.findByText(/regole PAC sono definite per singolo portafoglio/)).toBeInTheDocument();
    const newPacRule = screen.getByRole('button', { name: 'Nuova regola PAC' });
    expect(newPacRule).toBeDisabled();

    expect(api.paths().some((path) => path.includes('cash') || path.includes('pac'))).toBe(false);
    expect(api.writes()).toEqual([]);
  });

  it('ignores the mobile quick actions that would write', async () => {
    const { api } = renderAggregatePortfolio('/portfolio?azione=nuova-transazione');
    await screen.findByText('VWCE', { selector: 'p' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });

  it('on mobile shows the portfolio on each row and no edit/delete in the details sheet', async () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes('max-width: 48em'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      const { api } = renderAggregatePortfolio();
      const row = await screen.findByRole('button', { name: 'Acquisto VWCE: dettagli' });
      expect(row).toHaveTextContent('Core');
      fireEvent.click(row);
      expect(await screen.findByText('Seleziona un solo portafoglio per modificare')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Elimina transazione' })).not.toBeInTheDocument();
      expect(api.writes()).toEqual([]);
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it('keeps the write actions for a single portfolio', async () => {
    storeScope({ mode: 'single', id: 1 });
    const api = installFetchMock(PORTFOLIOS);
    renderWithApp(<PortfolioPage />);

    await waitFor(() => expect(api.paths()).toContain('/portfolios/1/transactions'));
    expect(await screen.findByRole('button', { name: 'Nuova Transazione' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Importa' })).toBeEnabled();
    expect(screen.queryByRole('columnheader', { name: 'Portafoglio' })).not.toBeInTheDocument();
  });
});
