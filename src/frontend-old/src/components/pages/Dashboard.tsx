import * as React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowUpCircle, ArrowDownCircle, TrendingUp, TrendingDown } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "../../lib/utils";

// --- DATA TYPES & MOCK DATA ---

type Position = {
  id: string;
  name: string;
  ticker: string;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  weight: number;
};

const mockPositions: Position[] = [
    { id: 'VT', name: 'Vanguard Total World Stock ETF', ticker: 'VT', market_value: 60960.31, unrealized_pl: 11510.91, unrealized_pl_pct: 23.45, weight: 53.77 },
    { id: 'GOOG', name: 'Alphabet Inc.', ticker: 'GOOG', market_value: 11981.20, unrealized_pl: 4506.40, unrealized_pl_pct: 60.29, weight: 10.57 },
    { id: 'IBIT', name: 'iShares Bitcoin Trust', ticker: 'IBIT', market_value: 6346.00, unrealized_pl: -2894.11, unrealized_pl_pct: -31.32, weight: 5.60 },
    { id: 'BNDW', name: 'Vanguard Total World Bond ETF', ticker: 'BNDW', market_value: 5630.31, unrealized_pl: 73.71, unrealized_pl_pct: 1.33, weight: 4.97 },
    { id: 'CASH', name: 'Cash', ticker: 'USD', market_value: 12428.20, unrealized_pl: 0.00, unrealized_pl_pct: 0.00, weight: 10.96 },
];


const mockTimeSeries = [
  { date: 'Gen', value: 90000 },
  { date: 'Feb', value: 92000 },
  { date: 'Mar', value: 88000 },
  { date: 'Apr', value: 95000 },
  { date: 'Mag', value: 98000 },
  { date: 'Giu', value: 105000 },
  { date: 'Lug', value: 102000 },
  { date: 'Ago', value: 108000 },
  { date: 'Set', value: 106000 },
  { date: 'Ott', value: 110000 },
  { date: 'Nov', value: 109000 },
  { date: 'Dic', value: 113346.02 },
];

const totalMarketValue = mockPositions.reduce((sum, pos) => sum + pos.market_value, 0);
const totalUnrealizedPL = mockPositions.reduce((sum, pos) => sum + pos.unrealized_pl, 0);
const costBasis = totalMarketValue - totalUnrealizedPL;
const totalUnrealizedPLPct = costBasis !== 0 ? (totalUnrealizedPL / costBasis) * 100 : 0;


// --- HELPER FUNCTIONS ---

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
};

const formatPercentage = (value: number) => {
    return `${value.toFixed(2)}%`;
}

// --- TABLE COLUMNS DEFINITION ---

const columns: ColumnDef<Position>[] = [
  {
    accessorKey: "name",
    header: "Nome",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.name}</div>
        <div className="text-sm text-muted-foreground">{row.original.ticker}</div>
      </div>
    ),
  },
  {
    accessorKey: "market_value",
    header: () => <div className="text-right">Valore di Mercato</div>,
    cell: ({ row }) => <div className="text-right">{formatCurrency(row.getValue("market_value"))}</div>,
  },
  {
    accessorKey: "unrealized_pl",
    header: () => <div className="text-right">P/L non realizzato</div>,
    cell: ({ row }) => {
      const amount = parseFloat(row.getValue("unrealized_pl"));
      const isPositive = amount >= 0;
      return (
        <div className={cn("text-right flex items-center justify-end gap-2", isPositive ? "text-green-500" : "text-red-500")}>
          {isPositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          {formatCurrency(amount)}
        </div>
      );
    },
  },
  {
      accessorKey: 'unrealized_pl_pct',
      header: () => <div className="text-right">P/L %</div>,
      cell: ({ row }) => {
          const percentage = parseFloat(row.getValue("unrealized_pl_pct"));
          const isPositive = percentage >= 0;
          return (
              <div className={cn("text-right", isPositive ? "text-green-500" : "text-red-500")}>
                  {formatPercentage(percentage)}
              </div>
          );
      }
  },
  {
    accessorKey: "weight",
    header: () => <div className="text-right">Allocazione</div>,
    cell: ({ row }) => <div className="text-right">{formatPercentage(row.getValue("weight"))}</div>,
  },
];


// --- MAIN DASHBOARD COMPONENT ---

const Dashboard = () => {
    const [sorting, setSorting] = React.useState<SortingState>([]);
    const data = React.useMemo(() => mockPositions, []);

    const table = useReactTable({
        data,
        columns,
        state: {
            sorting,
        },
        onSortingChange: setSorting,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
    });

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-8">
        <h1 className="text-3xl font-bold tracking-tight">Panoramica</h1>
        
        {/* KPI Cards */}
        <div className="grid gap-4 md:grid-cols-3">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Valore Totale Portafoglio</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{formatCurrency(totalMarketValue)}</div>
                    <p className="text-xs text-muted-foreground">Valore totale di tutti gli asset.</p>
                </CardContent>
            </Card>
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">P/L non realizzato</CardTitle>
                    {totalUnrealizedPL >= 0 ? <ArrowUpCircle className="h-4 w-4 text-green-500" /> : <ArrowDownCircle className="h-4 w-4 text-red-500" />}
                </CardHeader>
                <CardContent>
                    <div className={cn("text-2xl font-bold", totalUnrealizedPL >= 0 ? "text-green-500" : "text-red-500")}>
                        {formatCurrency(totalUnrealizedPL)}
                    </div>
                    <p className="text-xs text-muted-foreground">{formatPercentage(totalUnrealizedPLPct)} dal costo totale</p>
                </CardContent>
            </Card>
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Performance (YTD)</CardTitle>
                    {/* Placeholder for YTD performance */}
                    <ArrowUpCircle className="h-4 w-4 text-green-500" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold text-green-500">+12.5%</div>
                    <p className="text-xs text-muted-foreground">Rendimento da inizio anno.</p>
                </CardContent>
            </Card>
        </div>

        {/* Chart & Table */}
        <div className="grid gap-8 lg:grid-cols-1">
            <Card>
                <CardHeader>
                    <CardTitle>Performance Storica</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] p-0">
                     <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={mockTimeSeries}>
                            <defs>
                                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.8}/>
                                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--muted))" />
                            <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                            <YAxis 
                                stroke="hsl(var(--muted-foreground))"
                                fontSize={12}
                                tickFormatter={(value) => formatCurrency(value)}
                                domain={['auto', 'auto']}
                            />
                            <Tooltip 
                                contentStyle={{ 
                                    backgroundColor: "hsl(var(--card))",
                                    borderColor: "hsl(var(--border))"
                                }}
                                labelFormatter={(value: number) => [formatCurrency(value), "Valore"]}
                            />
                            <Area type="monotone" dataKey="value" stroke="hsl(var(--primary))" fill="url(#colorValue)" />
                        </AreaChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader>
                    <CardTitle>Le mie Posizioni</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            {table.getHeaderGroups().map((headerGroup) => (
                                <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => {
                                    return (
                                    <TableHead key={header.id} onClick={() => header.column.getToggleSortingHandler()?.(event)}>
                                        {header.isPlaceholder
                                        ? null
                                        : flexRender(
                                            header.column.columnDef.header,
                                            header.getContext()
                                            )}
                                        {{
                                          asc: ' 🔼',
                                          desc: ' 🔽',
                                        }[header.column.getIsSorted() as string] ?? null}
                                    </TableHead>
                                    );
                                })}
                                </TableRow>
                            ))}
                        </TableHeader>
                        <TableBody>
                            {table.getRowModel().rows?.length ? (
                                table.getRowModel().rows.map((row) => (
                                <TableRow
                                    key={row.id}
                                    data-state={row.getIsSelected() && "selected"}
                                >
                                    {row.getVisibleCells().map((cell) => (
                                    <TableCell key={cell.id}>
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                    ))}
                                </TableRow>
                                ))
                            ) : (
                                <TableRow>
                                <TableCell colSpan={columns.length} className="h-24 text-center">
                                    Nessun risultato.
                                </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    </div>
  );
};

export default Dashboard;
