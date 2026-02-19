import Button from "../atoms/Button";
import Panel from "../atoms/Panel";

type OpsPanelProps = {
  loading: boolean;
  refreshingPrices: boolean;
  runningBackfill: boolean;
  onRefreshPrices: () => Promise<void>;
  onBackfillOneYear: () => Promise<void>;
};

function OpsPanel({ loading, refreshingPrices, runningBackfill, onRefreshPrices, onBackfillOneYear }: OpsPanelProps) {
  return (
    <Panel title="Operazioni Dati" className="ops-panel">
      <div className="ops-actions">
        <Button type="button" variant="secondary" onClick={() => void onRefreshPrices()} disabled={refreshingPrices || loading}>
          {refreshingPrices ? "Refresh in corso..." : "Refresh prezzi ora"}
        </Button>
        <Button type="button" variant="secondary" onClick={() => void onBackfillOneYear()} disabled={runningBackfill || loading}>
          {runningBackfill ? "Backfill in corso..." : "Backfill 1Y"}
        </Button>
      </div>
    </Panel>
  );
}

export default OpsPanel;
