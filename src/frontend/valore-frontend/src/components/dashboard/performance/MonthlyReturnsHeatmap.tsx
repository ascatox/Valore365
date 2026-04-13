import { Card, Group, Loader, Table, Text } from '@mantine/core';
import { useComputedColorScheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { formatPct, formatShortDate } from '../formatters';
import { heatmapCellColors, MONTH_LABELS } from './utils';

interface MonthlyMatrixRow {
  year: number;
  months: Record<number, number>;
  yearReturn: number | null;
}

interface MonthlyReturnsHeatmapProps {
  matrix: MonthlyMatrixRow[];
  loading: boolean;
  startDate?: string;
  endDate?: string;
}

export function MonthlyReturnsHeatmap({ matrix, loading, startDate, endDate }: MonthlyReturnsHeatmapProps) {
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
        <Text fw={600}>Heatmap rendimenti mensili</Text>
        {startDate && endDate && (
          <Text size="xs" c="dimmed">
            {formatShortDate(startDate)} - {formatShortDate(endDate)}
          </Text>
        )}
      </Group>
      {loading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">Calcolo rendimenti mensili...</Text>
        </Group>
      ) : matrix.length === 0 ? (
        <Text size="sm" c="dimmed">Nessun mese disponibile nel periodo selezionato.</Text>
      ) : (
        <Table
          withTableBorder={false}
          highlightOnHover={false}
          styles={{
            td: { padding: 6, borderBottom: 'none' },
            th: { padding: '0 6px 8px 6px', borderBottom: 'none' },
          }}
        >
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Anno</Table.Th>
              {MONTH_LABELS.map((month) => (
                <Table.Th key={month} ta="center">{month}</Table.Th>
              ))}
              <Table.Th ta="center">YTD</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {matrix.map((row) => (
              <Table.Tr key={row.year}>
                <Table.Td>
                  <Text fw={700}>{row.year}</Text>
                </Table.Td>
                {MONTH_LABELS.map((_, index) => {
                  const value = row.months[index + 1] ?? null;
                  const colors = heatmapCellColors(value, isDark);
                  return (
                    <Table.Td key={`${row.year}-${index + 1}`} ta="center">
                      <div
                        style={{
                          minWidth: isMobile ? 58 : 64,
                          borderRadius: 10,
                          padding: '8px 6px',
                          background: colors.background,
                          color: colors.color,
                          border: colors.border,
                          fontSize: 12,
                          fontWeight: 700,
                        }}
                      >
                        {value == null ? '\u2014' : formatPct(value)}
                      </div>
                    </Table.Td>
                  );
                })}
                <Table.Td ta="center">
                  <div
                    style={{
                      minWidth: isMobile ? 68 : 74,
                      borderRadius: 10,
                      padding: '8px 6px',
                      background: heatmapCellColors(row.yearReturn, isDark).background,
                      color: heatmapCellColors(row.yearReturn, isDark).color,
                      border: heatmapCellColors(row.yearReturn, isDark).border,
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    {row.yearReturn == null ? '\u2014' : formatPct(row.yearReturn)}
                  </div>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Card>
  );
}
