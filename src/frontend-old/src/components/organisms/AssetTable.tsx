
import * as React from "react"
import { 
  ColumnDef, 
  flexRender, 
  getCoreRowModel, 
  useReactTable 
} from "@tanstack/react-table"

import { Progress } from "@/components/ui/progress"
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from "@/components/ui/table"
import { AssetPosition } from "../../types/api"

export const columns: ColumnDef<AssetPosition>[] = [
  {
    accessorKey: "name",
    header: "Asset",
    cell: ({ row }) => (
      <div className="flex flex-col">
        <span className="font-bold text-white">{row.original.ticker}</span>
        <span className="text-sm text-slate-400">{row.original.name}</span>
      </div>
    ),
  },
  {
    accessorKey: "allocation_percent",
    header: () => <div className="text-right">Allocazione</div>,
    cell: ({ row }) => (
        <div className="hidden md:flex flex-col items-end">
            <span className="font-mono text-white">{row.original.allocation_percent.toFixed(2)}%</span>
            <Progress value={row.original.allocation_percent} className="w-[100px] bg-slate-700 h-2 mt-1" indicatorClassName="bg-indigo-600" />
        </div>
    ),
    
  },
  {
    accessorKey: "current_price",
    header: () => <div className="text-right">Prezzo</div>,
    cell: ({ row }) => (
      <div className="hidden md:block text-right font-mono text-white">
        {new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(row.original.current_price)}
      </div>
    ),
  },
  {
    accessorKey: "current_value",
    header: () => <div className="text-right">Valore</div>,
    cell: ({ row }) => (
        <div className="text-right">
            <div className="font-mono text-white">{new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(row.original.current_value)}</div>
        </div>
    ),
  },
  {
    accessorKey: "pnl_value",
    header: () => <div className="text-right">P&L</div>,
    cell: ({ row }) => {
      const pnl = row.original.pnl_value;
      const pnlPercent = row.original.pnl_percent;
      const isPositive = pnl >= 0;

      return (
        <div className={`text-right font-mono ${isPositive ? "text-emerald-500" : "text-rose-500"}`}>
          <div>{new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", signDisplay: "always" }).format(pnl)}</div>
          <div className="text-sm">{`(${pnlPercent.toFixed(2)}%)`}</div>
        </div>
      );
    },
  },
];

interface AssetTableProps {
  data: AssetPosition[];
}

export function AssetTable({ data }: AssetTableProps) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="border-slate-800">
              {headerGroup.headers.map((header) => {
                return (
                  <TableHead key={header.id} className="text-slate-400">
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                  </TableHead>
                )
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
                className="border-slate-800"
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
              <TableCell colSpan={columns.length} className="h-24 text-center text-slate-400">
                Nessun asset nel portafoglio.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
