import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TransactionListItem } from '../services/api';
import { apiError, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
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
    // The AI export is read-only: available in aggregate (TASK-29).
    expect(screen.getByRole('button', { name: /Esporta per AI/ })).toBeEnabled();

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

  it('exports the aggregate snapshot for AI: copy and .md download', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const markdown = '# Vista aggregata — Snapshot portafogli\n\nVista aggregata: Core, Pensione\n';
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === `/portfolios/aggregate/transactions?${AGG}`) return AGGREGATE_TRANSACTIONS;
      if (request.path === `/portfolios/aggregate/export/markdown?${AGG}`) {
        return new Response(markdown, {
          status: 200,
          headers: {
            'Content-Type': 'text/markdown; charset=utf-8',
            'Content-Disposition': 'attachment; filename="valore365-aggregato-2026-10-31.md"',
          },
        });
      }
      return undefined;
    });
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const createObjectURL = vi.fn(() => 'blob:md');
    const revokeObjectURL = vi.fn();
    Object.assign(window.URL, { createObjectURL, revokeObjectURL });
    const downloads: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push(this.download);
    });

    renderWithApp(<PortfolioPage />);
    await screen.findByText('VWCE', { selector: 'p' });

    // Desktop menu: copy for AI.
    fireEvent.click(screen.getByRole('button', { name: /Esporta per AI/ }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /Copia negli appunti/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(markdown));
    expect(await screen.findByText(/Snapshot della vista aggregata copiato/)).toBeInTheDocument();

    // Switcher quick action in aggregate mode: download the .md.
    fireEvent.click(screen.getByText('Portfolio attivo').closest('button')!);
    expect(await screen.findByRole('button', { name: 'Copia per AI' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Elimina' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Scarica .md' }));
    await waitFor(() => expect(downloads).toEqual(['valore365-aggregato-2026-10-31.md']));

    expect(api.paths().filter((path) => path.includes('export/markdown'))).toEqual([
      `/portfolios/aggregate/export/markdown?${AGG}`,
      `/portfolios/aggregate/export/markdown?${AGG}`,
    ]);
    expect(api.paths().some((path) => /^\/portfolios\/\d+\/export/.test(path))).toBe(false);
    expect(api.writes()).toEqual([]);
    click.mockRestore();
  });

  it('recovers to a single portfolio when one of the aggregate was deleted elsewhere', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    let listCalls = 0;
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === '/portfolios') {
        listCalls += 1;
        // The first list is stale; the refetch no longer has "Pensione".
        return listCalls === 1 ? PORTFOLIOS : [PORTFOLIOS[0]];
      }
      if (request.path === `/portfolios/aggregate/transactions?${AGG}`) {
        return apiError(404, 'not_found', 'Portfolio non trovato');
      }
      return undefined;
    });
    renderWithApp(<PortfolioPage />);

    expect(await screen.findByText(/non esiste più/)).toBeInTheDocument();
    expect(screen.getByText('Vista aggregata aggiornata')).toBeInTheDocument();
    await waitFor(() => expect(api.paths()).toContain('/portfolios/1/transactions'));
    // The raw API message is not shown on the page.
    expect(screen.queryByText('Portfolio non trovato')).not.toBeInTheDocument();
    expect(screen.queryByText('Vista aggregata in sola lettura')).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem('valore365.portfolioScope')!)).toEqual({ mode: 'single', id: 1 });

    fireEvent.click(screen.getByRole('button', { name: 'Chiudi avviso' }));
    await waitFor(() => expect(screen.queryByText('Vista aggregata aggiornata')).not.toBeInTheDocument());
  });

  it('shows a friendly message when the aggregate export fails', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === `/portfolios/aggregate/transactions?${AGG}`) return AGGREGATE_TRANSACTIONS;
      if (request.path.startsWith('/portfolios/aggregate/export/markdown')) {
        return apiError(400, 'invalid_request', 'I portafogli aggregati devono avere la stessa valuta base');
      }
      return undefined;
    });
    renderWithApp(<PortfolioPage />);
    await screen.findByText('VWCE', { selector: 'p' });

    fireEvent.click(screen.getByRole('button', { name: /Esporta per AI/ }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /Scarica file .md/ }));

    expect((await screen.findAllByText(/hanno valute base diverse/)).length).toBeGreaterThan(0);
  });
});
