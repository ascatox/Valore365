import type { ReactNode } from 'react';
import { Card, Group, Loader, Select, Stack, Table, Text, TextInput, Title, UnstyledButton } from '@mantine/core';
import { IconChevronDown, IconChevronUp, IconSelector } from '@tabler/icons-react';

interface TransactionsSectionProps {
  loading: boolean;
  filterQuery: string;
  onFilterQueryChange: (value: string) => void;
  filterSide: string;
  onFilterSideChange: (value: string) => void;
  sortKey: string;
  onSortKeyChange: (value: string) => void;
  sortDir: string;
  onSortDirChange: (value: string) => void;
  rows: ReactNode;
  mobileCards?: ReactNode;
  hasRows: boolean;
  selectedPortfolioId: string | null;
  showActions?: boolean;
}

function SortIcon({ active, dir }: { active: boolean; dir: string }) {
  if (!active) return <IconSelector size={14} stroke={1.5} style={{ opacity: 0.4 }} />;
  return dir === 'asc' ? <IconChevronUp size={14} stroke={1.5} /> : <IconChevronDown size={14} stroke={1.5} />;
}

export function TransactionsSection({
  loading,
  filterQuery,
  onFilterQueryChange,
  filterSide,
  onFilterSideChange,
  sortKey,
  onSortKeyChange,
  sortDir,
  onSortDirChange,
  rows,
  mobileCards,
  hasRows,
  selectedPortfolioId,
  showActions = true,
}: TransactionsSectionProps) {
  const valueSortActive = sortKey === 'value';
  const handleValueSortToggle = () => {
    if (!valueSortActive) {
      onSortKeyChange('value');
      onSortDirChange('desc');
      return;
    }
    onSortDirChange(sortDir === 'asc' ? 'desc' : 'asc');
  };

  return (
    <Card withBorder mt="lg">
      <Group justify="space-between" mb="sm">
        <Title order={4}>Storico Transazioni</Title>
        {loading && (
          <Group gap="xs">
            <Loader size="xs" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>
      <Group mb="sm" grow visibleFrom="sm">
        <TextInput
          label="Filtro testo"
          placeholder="Ticker, nome asset, note"
          value={filterQuery}
          onChange={(event) => onFilterQueryChange(event.currentTarget.value)}
        />
        <Select
          label="Tipo"
          data={[
            { value: 'all', label: 'Tutti' },
            { value: 'buy', label: 'Acquisto' },
            { value: 'sell', label: 'Vendita' },
          ]}
          value={filterSide}
          onChange={(value) => onFilterSideChange(value ?? 'all')}
        />
        <Select
          label="Ordina per"
          data={[
            { value: 'trade_at', label: 'Data' },
            { value: 'symbol', label: 'Asset' },
            { value: 'side', label: 'Tipo' },
            { value: 'value', label: 'Valore' },
          ]}
          value={sortKey}
          onChange={(value) => onSortKeyChange(value ?? 'trade_at')}
        />
        <Select
          label="Direzione"
          data={[
            { value: 'desc', label: 'Decrescente' },
            { value: 'asc', label: 'Crescente' },
          ]}
          value={sortDir}
          onChange={(value) => onSortDirChange(value ?? 'desc')}
        />
      </Group>
      <Stack gap="sm" hiddenFrom="sm">
        {hasRows ? (
          mobileCards
        ) : (
          <Card withBorder>
            <Text c="dimmed" ta="center">
              {selectedPortfolioId ? 'Nessuna transazione presente' : 'Seleziona un portafoglio'}
            </Text>
          </Card>
        )}
      </Stack>

      <Table.ScrollContainer minWidth={600} visibleFrom="sm">
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Data</Table.Th>
              <Table.Th>Tipo</Table.Th>
              <Table.Th>Asset</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="sm">Qta</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="sm">Prezzo</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="md">Fee</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>
                <UnstyledButton
                  onClick={handleValueSortToggle}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Text fw={600} size="xs" component="span">Valore</Text>
                  <SortIcon active={valueSortActive} dir={sortDir} />
                </UnstyledButton>
              </Table.Th>
              {showActions && <Table.Th style={{ textAlign: 'right' }}>Azioni</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {hasRows ? (
              rows
            ) : (
              <Table.Tr>
                <Table.Td colSpan={showActions ? 8 : 7}>
                  <Text c="dimmed" ta="center">
                    {selectedPortfolioId ? 'Nessuna transazione presente' : 'Seleziona un portafoglio'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}
