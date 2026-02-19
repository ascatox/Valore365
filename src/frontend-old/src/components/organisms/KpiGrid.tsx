const StatCard = ({ title, value, isCurrency = true }) => {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
      <h3 className="text-slate-400 text-sm font-medium">{title}</h3>
      <p className="text-white text-2xl font-semibold">{value}</p>
    </div>
  );
};

export const KpiGrid = ({ summary }) => {
  return (
    <>
        <StatCard title="Net Worth" value={`€${summary.net_worth.toFixed(2)}`} />
        <StatCard title="P&L Totale" value={`€${summary.total_pnl.toFixed(2)}`} />
        <StatCard title="Day Change" value={`${summary.day_change_percent.toFixed(2)}%`} isCurrency={false} />
        <StatCard title="Costi Annuali TER" value={`${summary.annual_ter.toFixed(2)}%`} isCurrency={false} />
    </>
  );
};