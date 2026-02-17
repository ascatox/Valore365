import { PieChart, Pie, Cell, ResponsiveContainer, Legend } from 'recharts';

const COLORS = ['#059669', '#FBBF24', '#D97706', '#4F46E5'];

export const AssetAllocation = ({ allocation }) => {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
        <h3 className="text-white text-lg font-semibold mb-4">Asset Allocation</h3>
        <ResponsiveContainer width="100%" height={300}>
            <PieChart>
                <Pie
                    data={allocation}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                >
                    {allocation.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                </Pie>
                <Legend />
            </PieChart>
        </ResponsiveContainer>
    </div>
  );
};