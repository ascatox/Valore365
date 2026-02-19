
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { HistoryPoint } from '../../types/api';
import { Skeleton } from '@/components/ui/skeleton';

interface PortfolioChartProps {
  data: HistoryPoint[];
  isLoading: boolean;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-900 border border-slate-700 rounded-md p-2 text-sm">
        <p className="label text-slate-400">{`Data: ${label}`}</p>
        <p className="intro text-white">{`Valore: ${new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(payload[0].value)}`}</p>
      </div>
    );
  }

  return null;
};

const PortfolioChart = ({ data, isLoading }: PortfolioChartProps) => {
  if (isLoading) {
    return <Skeleton className="h-[300px] w-full animate-pulse" />;
  }

  const trendIsPositive = data.length > 1 ? data[data.length - 1].value >= data[0].value : true;
  const gradientColor = trendIsPositive ? 'emerald' : 'rose';

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 5, right: 0, left: 0, bottom: 5 }}>
        <defs>
          <linearGradient id="colorUv" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={`var(--color-${gradientColor}-500)`} stopOpacity={0.8} />
            <stop offset="95%" stopColor={`var(--color-${gradientColor}-500)`} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis 
          dataKey="date" 
          tickFormatter={(tick) => new Date(tick).toLocaleDateString('it-IT', { month: 'short', year: '2-digit' })}
          stroke="var(--color-slate-500)"
          dy={10}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area type="monotone" dataKey="value" stroke={`var(--color-${gradientColor}-500)`} fillOpacity={1} fill="url(#colorUv)" />
      </AreaChart>
    </ResponsiveContainer>
  );
};

export default PortfolioChart;
