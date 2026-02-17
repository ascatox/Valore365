const holdingsData = [
  { name: 'Vanguard Total World Stock Index Fund ETF Shares', ticker: 'VT', date: '28/10/2020', value: '60.960,31', alloc: '53,77%', change: '+ 11.510,91', perf: '+ 23,45%', color: 'bg-red-500' },
  { name: 'USD (Contanti)', ticker: 'USD', date: '01/01/2024', value: '12.428,20', alloc: '10,96%', change: '0,00', perf: '0,00%', color: 'bg-slate-500' },
  { name: 'Alphabet Inc.', ticker: 'GOOG', date: '16/07/2018', value: '11.981,20', alloc: '10,57%', change: '+ 4.506,40', perf: '+ 60,29%', color: 'bg-red-600' },
  { name: 'iShares Bitcoin Trust', ticker: 'IBIT', date: '12/03/2024', value: '6.346,00', alloc: '5,60%', change: '- 2.894,11', perf: '- 31,32%', color: 'bg-black' },
  { name: 'Vanguard Total World Bond ETF', ticker: 'BNDW', date: '23/02/2024', value: '5.630,31', alloc: '4,97%', change: '+ 73,71%', perf: '+ 1,33%', color: 'bg-red-500' },
];

const Holdings = () => {
  return (
    <div className="flex flex-col bg-slate-950 px-8 py-12">
      <div className="flex items-center justify-between mb-12">
        <h2 className="text-4xl font-bold text-white tracking-tight">Partecipazioni</h2>
        <div className="flex gap-2 bg-slate-900 p-1 rounded-lg">
          <button className="px-4 py-1 bg-slate-800 text-white rounded-md text-sm font-medium">Attivo</button>
          <button className="px-4 py-1 text-slate-400 text-sm font-medium">Chiuso</button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-slate-500 text-xs font-semibold uppercase tracking-wider border-b border-slate-900">
              <th className="pb-4 px-4">Nome</th>
              <th className="pb-4 px-4">Prima attività</th>
              <th className="pb-4 px-4 text-right">Valore</th>
              <th className="pb-4 px-4 text-right">Allocazione ↓</th>
              <th className="pb-4 px-4 text-right">Cambia</th>
              <th className="pb-4 px-4 text-right">Prestazione</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-900">
            {holdingsData.map((item, i) => (
              <tr key={i} className="group hover:bg-slate-900/40 transition-colors">
                <td className="py-5 px-4 flex items-center gap-4">
                  <div className={`w-8 h-8 ${item.color} rounded flex items-center justify-center text-[10px] font-bold text-white uppercase`}>
                    {item.ticker.slice(0, 1)}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-200 group-hover:text-white transition-colors">{item.name}</div>
                    <div className="text-xs text-slate-500 font-medium uppercase">{item.ticker}</div>
                  </div>
                </td>
                <td className="py-5 px-4 text-sm text-slate-400 font-medium">{item.date}</td>
                <td className="py-5 px-4 text-sm text-slate-200 text-right font-semibold">{item.value}</td>
                <td className="py-5 px-4 text-sm text-slate-400 text-right font-medium">{item.alloc}</td>
                <td className={`py-5 px-4 text-sm text-right font-semibold ${item.change.startsWith('+') ? 'text-emerald-500' : item.change === '0,00' ? 'text-slate-400' : 'text-rose-500'}`}>
                  {item.change}
                </td>
                <td className={`py-5 px-4 text-sm text-right font-semibold ${item.perf.startsWith('+') ? 'text-emerald-500' : item.perf === '0,00%' ? 'text-slate-400' : 'text-rose-500'}`}>
                  {item.perf}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Holdings;
