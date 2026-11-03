import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CashBalanceResponse } from '../../../services/api';
import { CashSection } from './CashSection';

const getPortfolioCashBalanceMock = vi.fn();

vi.mock('../../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../../services/api')>('../../../services/api');
  return {
    ...actual,
    getPortfolioCashBalance: (...args: unknown[]) => getPortfolioCashBalanceMock(...args),
  };
});

// methodology.md section 9.1: deposit 1000, buy 8 x 100, sell 3 x 110,
// dividend 20 net of 5.20 tax -> cash 544.80 (TASK-49 cash model).
const response: CashBalanceResponse = {
  portfolio_id: 1,
  total_cash: 544.8,
  currency_breakdown: [{ currency: 'EUR', balance: 544.8 }],
  recent_movements: [],
  fx_missing_currencies: [],
  implicit_contributions_total: 0,
  cash_breakdown: {
    opening_balance: 0,
    deposits: 1000,
    withdrawals: 0,
    dividends: 14.8,
    interest: 0,
    fees: 0,
    buys: 800,
    sells: 330,
    implicit_contributions: 0,
  },
  cash_model_note: 'Liquidita calcolata con lo stesso modello della performance.',
};

describe('CashSection', () => {
  beforeEach(() => {
    getPortfolioCashBalanceMock.mockReset();
  });

  it('shows the cash breakdown with buys and sells, adding up to the total', async () => {
    getPortfolioCashBalanceMock.mockResolvedValue(response);

    render(
      <MantineProvider>
        <CashSection selectedPortfolioId="1" baseCurrency="EUR" />
      </MantineProvider>,
    );

    const breakdown = await screen.findByTestId('cash-breakdown');
    const box = within(breakdown);
    expect(box.getByText('Depositi')).toBeInTheDocument();
    expect(box.getByText('Acquisti')).toBeInTheDocument();
    expect(box.getByText('−800,00')).toBeInTheDocument();
    expect(box.getByText('Vendite')).toBeInTheDocument();
    expect(box.getByText('+330,00')).toBeInTheDocument();
    expect(box.getByText('Dividendi netti')).toBeInTheDocument();
    // Zero lines are hidden.
    expect(box.queryByText('Prelievi')).not.toBeInTheDocument();
    expect(box.queryByText('Apporti impliciti')).not.toBeInTheDocument();
    expect(box.getByText('Liquidita calcolata con lo stesso modello della performance.')).toBeInTheDocument();

    const lines = response.cash_breakdown!;
    const sum =
      lines.opening_balance + lines.deposits - lines.withdrawals + lines.dividends + lines.interest
      - lines.fees - lines.buys + lines.sells + lines.implicit_contributions;
    expect(sum).toBeCloseTo(response.total_cash, 2);
  });

  it('works without a breakdown (older backend)', async () => {
    getPortfolioCashBalanceMock.mockResolvedValue({ ...response, cash_breakdown: undefined, cash_model_note: undefined });

    render(
      <MantineProvider>
        <CashSection selectedPortfolioId="1" baseCurrency="EUR" />
      </MantineProvider>,
    );

    expect(await screen.findByText('Saldo Totale')).toBeInTheDocument();
    expect(screen.queryByTestId('cash-breakdown')).not.toBeInTheDocument();
  });
});
