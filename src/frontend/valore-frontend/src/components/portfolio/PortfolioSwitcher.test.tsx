import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio } from '../../services/api';
import type { PortfolioScope } from '../../scope/portfolioScope';
import { PortfolioSwitcher } from './PortfolioSwitcher';

const portfolio = (id: number, name: string, base_currency = 'EUR'): Portfolio => ({
  id,
  name,
  base_currency,
  timezone: 'Europe/Rome',
  target_notional: null,
  cash_balance: 100,
  created_at: '2026-01-01T00:00:00Z',
});

const PORTFOLIOS = [portfolio(1, 'Core'), portfolio(2, 'Pensione'), portfolio(3, 'Dollari', 'USD')];

const originalMatchMedia = window.matchMedia;

// Mantine's ScrollArea observes its size; jsdom has no ResizeObserver.
if (!('ResizeObserver' in window)) {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
}

function mockMobile() {
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
}

function renderSwitcher(props: Partial<Parameters<typeof PortfolioSwitcher>[0]> = {}) {
  const onChange = vi.fn();
  const onScopeChange = vi.fn();
  const onEditPortfolio = vi.fn();
  render(
    <MantineProvider>
      <PortfolioSwitcher
        portfolios={PORTFOLIOS}
        value="1"
        onChange={onChange}
        onEditPortfolio={onEditPortfolio}
        {...props}
        onScopeChange={props.onScopeChange ?? onScopeChange}
      />
    </MantineProvider>,
  );
  return { onChange, onScopeChange, onEditPortfolio };
}

const openSwitcher = () => fireEvent.click(screen.getByText('Portfolio attivo').closest('button')!);
const checkboxFor = (name: string) => screen.getByRole('checkbox', { name: `Includi ${name} nella vista aggregata` });

describe('PortfolioSwitcher', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('without allowAggregate behaves as before: no aggregate section, single selection only', async () => {
    const { onChange, onScopeChange } = renderSwitcher();
    openSwitcher();
    expect(await screen.findByText('Tutti i portafogli')).toBeInTheDocument();
    expect(screen.queryByText('Vista aggregata')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.getByRole('button', { name: /Modifica/ })).toBeInTheDocument();

    fireEvent.click(screen.getByText('Pensione').closest('button')!);
    expect(onChange).toHaveBeenCalledWith('2');
    expect(onScopeChange).not.toHaveBeenCalled();
  });

  it('multi-selects portfolios with the same base currency', async () => {
    const { onScopeChange } = renderSwitcher({ allowAggregate: true, scope: { mode: 'single', id: 1 } });
    openSwitcher();
    expect(await screen.findByText('Vista aggregata')).toBeInTheDocument();

    // The current portfolio is checked and cannot be removed on its own.
    expect(checkboxFor('Core')).toBeChecked();
    expect(checkboxFor('Core')).toBeDisabled();
    // Another base currency: disabled with a hint.
    expect(checkboxFor('Dollari')).toBeDisabled();
    expect(screen.getByText('Valuta USD: non aggregabile con EUR')).toBeInTheDocument();

    fireEvent.click(checkboxFor('Pensione'));
    expect(onScopeChange).toHaveBeenCalledWith({ mode: 'aggregate', ids: [1, 2] });
    // Edit/clone/delete stay available in single mode.
    expect(screen.getByRole('button', { name: /Modifica/ })).toBeInTheDocument();
  });

  it('selecting a portfolio from the list goes back to a single scope', async () => {
    const { onChange, onScopeChange } = renderSwitcher({ allowAggregate: true, scope: { mode: 'single', id: 1 } });
    openSwitcher();
    fireEvent.click((await screen.findByText('Pensione', { selector: 'p' })).closest('button')!);
    expect(onChange).toHaveBeenCalledWith('2');
    expect(onScopeChange).toHaveBeenCalledWith({ mode: 'single', id: 2 });
  });

  it('shows the aggregate on the trigger and hides single-portfolio actions', async () => {
    const scope: PortfolioScope = { mode: 'aggregate', ids: [1, 2] };
    const { onChange, onScopeChange } = renderSwitcher({ allowAggregate: true, scope, aggregateTotalValue: 12345 });

    expect(screen.getByText('Vista aggregata')).toBeInTheDocument();
    expect(screen.getByText('Aggregato (2)')).toBeInTheDocument();
    expect(screen.getByText(/Totale/)).toHaveTextContent(/12\.345/);
    expect(screen.getByText(/Core, Pensione/)).toBeInTheDocument();

    openSwitcher();
    expect(await screen.findByRole('button', { name: 'Torna a un solo portafoglio' })).toBeInTheDocument();
    expect(checkboxFor('Core')).toBeChecked();
    expect(checkboxFor('Core')).not.toBeDisabled();
    expect(checkboxFor('Pensione')).toBeChecked();
    expect(screen.queryByRole('button', { name: /Modifica/ })).not.toBeInTheDocument();

    fireEvent.click(checkboxFor('Pensione'));
    expect(onScopeChange).toHaveBeenLastCalledWith({ mode: 'single', id: 1 });

    fireEvent.click(screen.getByRole('button', { name: 'Torna a un solo portafoglio' }));
    expect(onChange).toHaveBeenLastCalledWith('1');
    expect(onScopeChange).toHaveBeenLastCalledWith({ mode: 'single', id: 1 });
  });

  it('works in the mobile bottom sheet', async () => {
    mockMobile();
    const { onScopeChange } = renderSwitcher({ allowAggregate: true, scope: { mode: 'aggregate', ids: [1, 2] } });
    const chip = await screen.findByRole('button', { name: /Cambia portafoglio/ });
    expect(chip).toHaveTextContent('Aggregato (2)');

    fireEvent.click(chip);
    expect(await screen.findByText('Seleziona portafoglio')).toBeInTheDocument();
    expect(checkboxFor('Dollari')).toBeDisabled();
    fireEvent.click(checkboxFor('Core'));
    expect(onScopeChange).toHaveBeenCalledWith({ mode: 'single', id: 2 });
  });
});
