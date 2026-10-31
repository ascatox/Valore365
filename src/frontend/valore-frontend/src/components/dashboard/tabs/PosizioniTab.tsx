import { useMemo, useState } from 'react';
import { ActionIcon, Badge, Card, Group, Loader, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { HoldingsTable } from '../holdings/HoldingsTable';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { usePortfolioSummary, usePortfolioPositions, usePortfolioXray, useTargetAllocation } from '../hooks/queries';
import { reclassifyPortfolioAssets, refreshPortfolioPrices } from '../../../services/api';
import type { AllocationDoughnutItem } from '../types';
import {
  isAggregateScope,
  scopePortfolioIds,
  singlePortfolioId,
  toPortfolioScope,
  type PortfolioScopeInput,
} from '../../../scope/portfolioScope';
import { AggregateReadOnlyTooltip } from '../../../scope/AggregateReadOnly';
import { AGGREGATE_EMPTY_POSITIONS } from '../../../scope/aggregateLabels';

const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: 'Azioni',
  etf: 'ETF',
  crypto: 'Crypto',
  bond: 'Obbligazioni',
  cash: 'Liquidità',
  fund: 'Fondi',
};

interface PosizioniTabProps {
  /** Portfolio or aggregate scope (aggregate: merged positions, no target weights). */
  scope: PortfolioScopeInput;
}

export function PosizioniTab({ scope: scopeInput }: PosizioniTabProps) {
  const scope = toPortfolioScope(scopeInput);
  const isAggregate = isAggregateScope(scope);
  const portfolioId = singlePortfolioId(scope);
  const { data: summary } = usePortfolioSummary(scope);
  const { data: positions = [], isLoading, refetch } = usePortfolioPositions(scope);
  const { data: xrayData } = usePortfolioXray(scope);
  // Target weights are per portfolio: disabled (empty) in the aggregate view.
  const { data: targetAllocation = [] } = useTargetAllocation(scope);
  const currency = summary?.base_currency ?? 'EUR';
  const [reclassifying, setReclassifying] = useState(false);
  const [refreshingPrices, setRefreshingPrices] = useState(false);

  const targetMap = useMemo(() => {
    const map = new Map<number, number>();
    for (const item of targetAllocation) map.set(item.asset_id, item.weight_pct);
    return map;
  }, [targetAllocation]);

  const allocationByType = useMemo<AllocationDoughnutItem[]>(() => {
    const grouped = new Map<string, number>();
    for (const p of positions) {
      const type = p.asset_type || 'stock';
      grouped.set(type, (grouped.get(type) ?? 0) + p.weight);
    }
    return Array.from(grouped.entries())
      .map(([type, weight]) => ({
        name: ASSET_TYPE_LABELS[type] ?? type,
        value: Math.round(weight * 100) / 100,
      }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  const allocationByAsset = useMemo<AllocationDoughnutItem[]>(() => {
    const sorted = [...positions].sort((a, b) => b.weight - a.weight);
    const top = sorted.slice(0, 8);
    const rest = sorted.slice(8);
    const items: AllocationDoughnutItem[] = top.map((p) => ({
      name: p.symbol,
      value: Math.round(p.weight * 100) / 100,
      asset_id: p.asset_id,
    }));
    const otherWeight = rest.reduce((s, p) => s + p.weight, 0);
    if (otherWeight > 0) {
      items.push({ name: 'Altro', value: Math.round(otherWeight * 100) / 100 });
    }
    return items;
  }, [positions]);

  const countryDoughnutData = useMemo<AllocationDoughnutItem[]>(() => {
    if (!xrayData?.aggregated_country_exposure) return [];
    return Object.entries(xrayData.aggregated_country_exposure)
      .filter(([, value]) => value > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value]) => ({ name, value }));
  }, [xrayData]);

  const sectorDoughnutData = useMemo<AllocationDoughnutItem[]>(() => {
    if (!xrayData?.aggregated_sector_exposure) return [];
    return Object.entries(xrayData.aggregated_sector_exposure)
      .filter(([, value]) => value > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value]) => ({ name, value }));
  }, [xrayData]);

  const handleReclassify = async () => {
    if (!portfolioId || reclassifying) return;
    setReclassifying(true);
    try {
      await reclassifyPortfolioAssets(portfolioId);
      await refetch();
    } finally {
      setReclassifying(false);
    }
  };

  const handleRefreshPrices = async () => {
    const portfolioIds = scopePortfolioIds(scope);
    if (!portfolioIds.length || refreshingPrices) return;
    setRefreshingPrices(true);
    try {
      for (const id of portfolioIds) {
        await refreshPortfolioPrices(id, 'all');
      }
      await refetch();
    } finally {
      setRefreshingPrices(false);
    }
  };

  if (isLoading) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Caricamento posizioni...</Text>
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" mb="md">
          <Text fw={600} size="sm">Posizioni correnti</Text>
          <Badge variant="light">{positions.length} posizioni</Badge>
        </Group>
        <HoldingsTable positions={positions} currency={currency} summary={summary ?? null} targetMap={targetMap} onRefreshPrices={handleRefreshPrices} refreshing={refreshingPrices} emptyMessage={isAggregate ? AGGREGATE_EMPTY_POSITIONS : undefined} />
      </Card>

      {positions.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <AllocationDoughnut
            title="Allocazione per tipo"
            data={allocationByType}
            centerLabel={`${positions.length}`}
            headerRight={
              isAggregate ? (
                <AggregateReadOnlyTooltip active>
                  <ActionIcon variant="subtle" size="sm" disabled aria-label="Reclassifica tipi">
                    <IconRefresh size={14} />
                  </ActionIcon>
                </AggregateReadOnlyTooltip>
              ) : (
              <Tooltip label="Reclassifica tipi da yFinance" withArrow>
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  loading={reclassifying}
                  onClick={handleReclassify}
                  aria-label="Reclassifica tipi"
                >
                  <IconRefresh size={14} />
                </ActionIcon>
              </Tooltip>
              )
            }
          />
          <AllocationDoughnut
            title="Allocazione per titolo"
            data={allocationByAsset}
            centerLabel={currency}
          />
        </SimpleGrid>
      )}

      {(countryDoughnutData.length > 0 || sectorDoughnutData.length > 0) && (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          {countryDoughnutData.length > 0 && (
            <AllocationDoughnut
              title="Allocazione Geografica"
              data={countryDoughnutData}
              centerLabel={`${countryDoughnutData.length}`}
              headerRight={<Badge variant="light" color="blue" size="sm">justETF</Badge>}
            />
          )}
          {sectorDoughnutData.length > 0 && (
            <AllocationDoughnut
              title="Allocazione Settoriale"
              data={sectorDoughnutData}
              centerLabel={`${sectorDoughnutData.length}`}
              headerRight={<Badge variant="light" color="blue" size="sm">justETF</Badge>}
            />
          )}
        </SimpleGrid>
      )}
    </Stack>
  );
}
