import { Table, Text } from '@mantine/core';
import { formatPct, formatDateTime, getVariationColor } from '../formatters';
import type { PerformerItem } from '../types';

interface PerformersTableProps {
  performers: PerformerItem[];
}

export function PerformersTable({ performers }: PerformersTableProps) {
  return (
    <Table.ScrollContainer minWidth={400}>
    <Table verticalSpacing="xs" striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Asset</Table.Th>
          <Table.Th style={{ textAlign: 'right' }}>Tipo</Table.Th>
          <Table.Th style={{ textAlign: 'right' }}>Rendimento</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {performers.length ? (
          performers.map((item, idx) => (
            <Table.Tr key={`${item.asset_id}-${idx}`}>
              <Table.Td>
                <Text size="sm" fw={500}>{item.symbol}</Text>
                <Text size="xs" c="dimmed">{item.name}</Text>
                {item.as_of ? <Text size="xs" c="dimmed">{formatDateTime(item.as_of)}</Text> : null}
              </Table.Td>
              <Table.Td align="right">Indice target</Table.Td>
              <Table.Td align="right">
                <Text c={getVariationColor(item.return_pct)} size="sm" fw={500}>
                  {formatPct(item.return_pct)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))
        ) : (
          <Table.Tr>
            <Table.Td colSpan={3}>
              <Text c="dimmed" size="sm" ta="center">Nessuna posizione disponibile</Text>
            </Table.Td>
          </Table.Tr>
        )}
      </Table.Tbody>
    </Table>
    </Table.ScrollContainer>
  );
}
