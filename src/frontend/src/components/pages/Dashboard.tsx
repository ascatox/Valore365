import { KpiGrid } from "../organisms/KpiGrid";
import { PortfolioTable } from "../organisms/PortfolioTable";
import { AssetAllocation } from "../organisms/AssetAllocation";
import { usePrivacy } from "../../contexts/PrivacyContext";
import { useQuery } from "../../hooks/useQuery"; // Assuming a custom hook for data fetching
import { Skeleton } from "../atoms/Skeleton"; // Assuming a Skeleton component

const Dashboard = () => {
  const { isPrivacyMode } = usePrivacy();
  // const { data: summary, isLoading: isLoadingSummary } = useQuery("/api/portfolio/1/summary"); // Example usage of a custom hook
  // const { data: positions, isLoading: isLoadingPositions } = useQuery("/api/portfolio/1/positions");
  // const { data: allocation, isLoading: isLoadingAllocation } = useQuery("/api/portfolio/1/allocation");

  // MOCKED DATA FOR NOW
  const isLoadingSummary = false;
  const isLoadingPositions = false;
  const isLoadingAllocation = false;

  const summary = {
    net_worth: 123456.78,
    total_pnl: 12345.67,
    day_change_percent: 1.23,
    annual_ter: 0.45
  };

  const positions = [
    { ticker: 'AAPL', name: 'Apple Inc.', quantity: 10, price: 175.23, total_value: 1752.30, weight: 14.20, pnl: 500.12 },
    { ticker: 'GOOGL', name: 'Alphabet Inc.', quantity: 5, price: 2800.00, total_value: 14000.00, weight: 11.34, pnl: -250.45 },
    { ticker: 'GLD', name: 'SPDR Gold Shares', quantity: 20, price: 180.50, total_value: 3610.00, weight: 2.92, pnl: 100.00 },
  ];

  const allocation = [
    { name: 'Azionario', value: 70 },
    { name: 'Obbligazionario', value: 15 },
    { name: 'Oro', value: 10 },
    { name: 'Liquidità', value: 5 },
  ];

  return (
    <div className="bg-slate-950 text-white min-h-screen">
      <div className="p-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {isLoadingSummary ? (
            <>
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </>
          ) : (
            <KpiGrid summary={summary} isPrivacyMode={isPrivacyMode} />
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            {isLoadingPositions ? (
              <Skeleton className="h-96" />
            ) : (
              <PortfolioTable positions={positions} isPrivacyMode={isPrivacyMode} />
            )}
          </div>
          <div>
            {isLoadingAllocation ? (
              <Skeleton className="h-96" />
            ) : (
              <AssetAllocation allocation={allocation} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
