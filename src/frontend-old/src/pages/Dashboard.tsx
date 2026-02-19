import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePrivacy } from '../contexts/PrivacyContext';
import PrivacyToggleButton from '../components/PrivacyToggleButton';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { Lectern } from 'lucide-react';

const data = [
  { name: 'Page A', uv: 4000, pv: 2400, amt: 2400 },
  { name: 'Page B', uv: 3000, pv: 1398, amt: 2210 },
  { name: 'Page C', uv: 2000, pv: 9800, amt: 2290 },
  { name: 'Page D', uv: 2780, pv: 3908, amt: 2000 },
  { name: 'Page E', uv: 1890, pv: 4800, amt: 2181 },
  { name: 'Page F', uv: 2390, pv: 3800, amt: 2500 },
  { name: 'Page G', uv: 3490, pv: 4300, amt: 2100 },
];

const Dashboard: React.FC = () => {
  const { context } = usePrivacy();

  const formatValue = (value: number | string) => {
    if (context) {
      return '*****';
    }
    return value;
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <PrivacyToggleButton />
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Saldo Totale</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatValue('€12,345.67')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-500">{formatValue('+5.2%')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>P&L Realizzato</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatValue('€1,234.56')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Valore Mercato</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatValue('€10,000.00')}</p>
          </CardContent>
        </Card>
      </div>
      <div className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>Grafico Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <LineChart width={500} height={300} data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="pv" stroke="#8884d8" activeDot={{ r: 8 }} />
              <Line type="monotone" dataKey="uv" stroke="#82ca9d" />
            </LineChart>
          </CardContent>
        </Card>
      </div>
      <div className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>Portafoglio</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Asset</TableHead>
                  <TableHead>Quantità</TableHead>
                  <TableHead>Prezzo</TableHead>
                  <TableHead>Valore</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>Bitcoin</TableCell>
                  <TableCell>{formatValue(1.23)}</TableCell>
                  <TableCell>{formatValue('€25,000')}</TableCell>
                  <TableCell>{formatValue('€30,750')}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Ethereum</TableCell>
                  <TableCell>{formatValue(10.5)}</TableCell>
                  <TableCell>{formatValue('€1,800')}</TableCell>
                  <TableCell>{formatValue('€18,900')}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
