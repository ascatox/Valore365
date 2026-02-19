export interface HistoryPoint {
  date: string; // ISO YYYY-MM-DD
  value: number; // Valore portafoglio in EUR
}

export interface AssetPosition {
  isin: string;
  ticker: string; // es. "VWCE"
  name: string;   // es. "Vanguard FTSE All-World..."
  quantity: number;
  avg_price: number; // Prezzo di carico
  current_price: number; // Prezzo realtime
  current_value: number; // quantity * current_price
  pnl_percent: number;   // ((current - avg) / avg) * 100
  pnl_value: number;
  allocation_percent: number; // Peso sul totale (0-100)
  category: "Equity" | "Bond" | "Gold" | "Cash";
}

export interface PortfolioSummary {
  net_worth: number;
  total_pnl_value: number;
  total_pnl_percent: number;
  day_change_percent: number;
  last_updated: string;
}
