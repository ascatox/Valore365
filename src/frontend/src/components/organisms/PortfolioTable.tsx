export const PortfolioTable = ({ positions }) => {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
        <h3 className="text-white text-lg font-semibold mb-4">Portfolio</h3>
        <div className="overflow-x-auto">
            <table className="w-full text-left">
                <thead>
                    <tr className="border-b border-slate-800">
                        <th className="p-2">Ticker</th>
                        <th className="p-2">Nome</th>
                        <th className="p-2">Quantità</th>
                        <th className="p-2">Prezzo</th>
                        <th className="p-2">Valore</th>
                        <th className="p-2">Peso %</th>
                        <th className="p-2">P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {positions.map((pos, i) => (
                        <tr key={i} className="border-b border-slate-800">
                            <td className="p-2">{pos.ticker}</td>
                            <td className="p-2">{pos.name}</td>
                            <td className="p-2">{pos.quantity}</td>
                            <td className="p-2">{`€${pos.price.toFixed(2)}`}</td>
                            <td className="p-2">{`€${pos.total_value.toFixed(2)}`}</td>
                            <td className="p-2">{`${pos.weight.toFixed(2)}%`}</td>
                            <td className={`p-2 ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {`€${pos.pnl.toFixed(2)}`}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    </div>
  );
};