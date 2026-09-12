import { Badge, Card, Group, Loader, Table, Text, Tooltip } from '@mantine/core';
import { formatPct, formatShortDate, getVariationColor } from '../formatters';
import { NdTooltip } from './NdTooltip';
import type { YearlyPerformanceResponse, YearlyPerformanceRow } from '../../../services/api/types';

interface YearlyReturnsTableProps {
  data: YearlyPerformanceResponse | undefined;
  loading: boolean;
}

function ndReason(row: YearlyPerformanceRow): string {
  if (!row.has_prices) return 'Nessuna quotazione storica disponibile per questo anno';
  return "MWR non calcolabile: flussi di cassa insufficienti o rendimento fuori dall'intervallo risolvibile";
}

function TwrCell({ row }: { row: YearlyPerformanceRow }) {
  if (row.twr_pct == null) {
    return <NdTooltip label={ndReason(row)}>N/D</NdTooltip>;
  }
  return (
    <Text fw={700} c={getVariationColor(row.twr_pct)}>
      {formatPct(row.twr_pct)}
    </Text>
  );
}

function MwrCell({ row }: { row: YearlyPerformanceRow }) {
  if (row.mwr_pct == null) {
    return <NdTooltip label={ndReason(row)}>N/D</NdTooltip>;
  }
  return (
    <Text fw={700} c={getVariationColor(row.mwr_pct)}>
      {formatPct(row.mwr_pct)}
    </Text>
  );
}

function PartialBadge({ row }: { row: YearlyPerformanceRow }) {
  if (!row.is_partial) return null;
  // The current calendar year (still in progress) reads "YTD"; an earlier
  // partial row can only be the inception year, so it reads "dal <data>".
  const isCurrentYear = row.year === new Date().getFullYear();
  const label = isCurrentYear ? 'YTD' : `dal ${formatShortDate(row.start_date) ?? row.start_date}`;
  return (
    <Badge size="xs" variant="light" ml={6}>
      {label}
    </Badge>
  );
}

export function YearlyReturnsTable({ data, loading }: YearlyReturnsTableProps) {
  const rows = [...(data?.rows ?? [])].reverse();

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
        <Text fw={600}>Rendimenti per anno</Text>
        {data?.start_date && data?.end_date && (
          <Text size="xs" c="dimmed">
            {formatShortDate(data.start_date)} - {formatShortDate(data.end_date)}
          </Text>
        )}
      </Group>

      {loading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">Calcolo rendimenti annuali...</Text>
        </Group>
      ) : rows.length === 0 ? (
        <Text size="sm" c="dimmed">Nessun anno disponibile.</Text>
      ) : (
        <Table.ScrollContainer minWidth={400}>
          <Table verticalSpacing="xs" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Anno</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>
                  <Tooltip label="Time-Weighted Return — rendimento del portafoglio al netto dei flussi di cassa" multiline w={280} withArrow>
                    <Text size="sm" fw={600} style={{ cursor: 'help', display: 'inline-block' }}>TWR</Text>
                  </Tooltip>
                </Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>
                  <Tooltip label="Money-Weighted Return — rendimento del periodo ponderato per i flussi di cassa dell'investitore, confrontabile con il TWR" multiline w={280} withArrow>
                    <Text size="sm" fw={600} style={{ cursor: 'help', display: 'inline-block' }}>MWR</Text>
                  </Tooltip>
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Table.Tr key={row.year}>
                  <Table.Td>
                    <Group gap={0} wrap="nowrap">
                      <Text fw={700}>{row.year}</Text>
                      <PartialBadge row={row} />
                    </Group>
                  </Table.Td>
                  <Table.Td align="right">
                    <TwrCell row={row} />
                  </Table.Td>
                  <Table.Td align="right">
                    <MwrCell row={row} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Card>
  );
}
