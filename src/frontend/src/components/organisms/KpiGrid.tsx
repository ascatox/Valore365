import type { PortfolioSummary } from "../../types";

type KpiGridProps = {
  summary: PortfolioSummary;
  deltaYear: number;
  currencyFormatter: Intl.NumberFormat;
  percentFormatter: Intl.NumberFormat;
};

function KpiGrid({ summary, deltaYear, currencyFormatter, percentFormatter }: KpiGridProps) {
  const pnlToneClass = summary.unrealized_pl >= 0 ? "tone-positive" : "tone-negative";
  const deltaToneClass = deltaYear >= 0 ? "tone-positive" : "tone-negative";

  return (
    <section className="kpi-grid">
      <article className="kpi-card">
        <h2>Valore Totale</h2>
        <p>{currencyFormatter.format(summary.market_value)}</p>
      </article>
      <article className="kpi-card">
        <h2>P/L Non Realizzato</h2>
        <p className={pnlToneClass}>
          {currencyFormatter.format(summary.unrealized_pl)} ({percentFormatter.format(summary.unrealized_pl_pct / 100)})
        </p>
      </article>
      <article className="kpi-card">
        <h2>Delta 1Y</h2>
        <p className={deltaToneClass}>{currencyFormatter.format(deltaYear)}</p>
      </article>
    </section>
  );
}

export default KpiGrid;
