import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PortfolioTargetDriftItem, Position } from '../../../services/api';
import { HoldingsTable } from './HoldingsTable';
import type { TargetDriftMap } from './targetDrift';

// Table.ScrollContainer measures itself; jsdom has no ResizeObserver.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

// Portfolio 9101 of the Auditor seed: 70.000 / 20.000 / 10.000 €, cash 9.256,50 €, targets 50/40/10.
function position(asset_id: number, symbol: string, value: number): Position {
  return {
    asset_id, symbol, name: symbol, asset_type: 'etf', quantity: value / 50, avg_cost: 50, market_price: 50,
    market_value: value, unrealized_pl: 0, unrealized_pl_pct: 0, day_change_pct: 0, weight: value / 1000,
    first_trade_at: null, price_stale: false,
  } as Position;
}

function drift(asset_id: number, symbol: string, target: number, current: number, value: number): PortfolioTargetDriftItem {
  return {
    asset_id, symbol, name: symbol, target_weight_pct: target, current_weight_pct: current,
    drift_pct: Math.round((current - target) * 100) / 100, market_value: value,
  };
}

const POSITIONS = [position(1, 'AUDEQ.MI', 70000), position(2, 'AUDBD.MI', 20000), position(3, 'AUDTECH.DE', 10000)];
// What GET /portfolios/9101/target-drift returns (same values as the Copilot get_target_drift):
// TASK-95, base = targeted holdings only (cash excluded) → 70 / 20 / 10.
const DRIFT: TargetDriftMap = new Map([
  [1, drift(1, 'AUDEQ.MI', 50, 70, 70000)],
  [2, drift(2, 'AUDBD.MI', 40, 20, 20000)],
  [3, drift(3, 'AUDTECH.DE', 10, 10, 10000)],
]);

function renderTable(targetMap?: TargetDriftMap) {
  return render(
    <MantineProvider>
      <HoldingsTable positions={POSITIONS} currency="EUR" targetMap={targetMap} />
    </MantineProvider>,
  );
}

describe('HoldingsTable drift from target (TASK-88)', () => {
  it('shows the drift of the backend, not one recomputed on the weight among positions', () => {
    renderTable(DRIFT);
    // TASK-95: +20 / −20 / 0 (with the TASK-85 base: +14,07 / −21,69 / −0,85).
    expect(screen.getByTestId('target-drift-3')).toHaveTextContent('0,00 pt');
    expect(screen.getByTestId('target-drift-1')).toHaveTextContent('+20,00 pt');
    expect(screen.getByTestId('target-drift-2')).toHaveTextContent('-20,00 pt');
    // «pt» never wraps alone: non-breaking space.
    expect(screen.getByTestId('target-drift-1').textContent).toBe('+20,00\u00a0pt');
    expect(screen.getAllByLabelText('Scostamento oltre 5 punti')).toHaveLength(2);
    const header = screen.getAllByRole('columnheader').find((th) => th.textContent?.includes('Target'));
    expect(header).toBeDefined();
    expect(within(header!).getByLabelText('Base dello scostamento')).toBeInTheDocument();
  });

  it('has no target column without drift data (aggregate view)', () => {
    renderTable(new Map());
    expect(screen.queryByTestId('target-drift-3')).toBeNull();
    expect(screen.getAllByRole('columnheader').some((th) => th.textContent?.includes('Target'))).toBe(false);
  });
});
