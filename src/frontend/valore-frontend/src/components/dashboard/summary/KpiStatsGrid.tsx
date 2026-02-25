import { SimpleGrid } from '@mantine/core';
import { KpiStatCard } from './KpiStatCard';
import type { KpiStatCardProps } from '../types';

interface KpiStatsGridProps {
  items: KpiStatCardProps[];
  cols?: { base: number; sm?: number; md?: number };
}

export function KpiStatsGrid({ items, cols = { base: 2, sm: 3, md: 5 } }: KpiStatsGridProps) {
  return (
    <SimpleGrid cols={cols} spacing="sm">
      {items.map((item) => (
        <KpiStatCard key={item.label} {...item} />
      ))}
    </SimpleGrid>
  );
}
