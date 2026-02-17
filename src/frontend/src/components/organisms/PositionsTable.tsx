import type { Position } from "../../types";
import Panel from "../atoms/Panel";

type PositionsTableProps = {
  positions: Position[];
};

function PositionsTable({ positions }: PositionsTableProps) {
  return (
    <Panel title="Posizioni">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Qty</th>
            <th>Avg Cost</th>
            <th>Market</th>
            <th>Value</th>
            <th>U/PnL%</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.asset_id}>
              <td>{position.symbol}</td>
              <td>{position.quantity}</td>
              <td>{position.avg_cost}</td>
              <td>{position.market_price}</td>
              <td>{position.market_value}</td>
              <td>{position.unrealized_pl_pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

export default PositionsTable;
