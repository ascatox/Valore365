import type { Position } from "../../types";
import Panel from "../atoms/Panel";

type AllocationBarsProps = {
  positions: Position[];
};

function AllocationBars({ positions }: AllocationBarsProps) {
  const total = positions.reduce((acc, position) => acc + position.market_value, 0);
  const rows = total <= 0
    ? []
    : positions.slice(0, 8).map((position) => ({
      symbol: position.symbol,
      weight: (position.market_value / total) * 100,
    }));

  return (
    <Panel title="Allocazione (Top Posizioni)">
      <div className="bar-list">
        {rows.map((row) => (
          <div className="bar-row" key={row.symbol}>
            <div className="bar-label">
              <span>{row.symbol}</span>
              <span>{row.weight.toFixed(2)}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.min(100, row.weight)}%` }} />
            </div>
          </div>
        ))}
        {rows.length === 0 && <p className="hint">Nessuna posizione disponibile.</p>}
      </div>
    </Panel>
  );
}

export default AllocationBars;
