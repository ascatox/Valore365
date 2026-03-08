import { Badge, Group, Modal, SimpleGrid, Stack, Table, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle, IconArrowsShuffle, IconBriefcase } from '@tabler/icons-react';
import type { PortfolioHealthAlert } from '../../services/api';

interface DoctorAlertDetailsModalProps {
  alert: PortfolioHealthAlert | null;
  opened: boolean;
  onClose: () => void;
  currency?: string;
}

interface HoldingDetail {
  symbol: string;
  name: string;
  asset_type?: string;
  weight_pct: number;
  market_value?: number;
}

interface OverlapPairDetail {
  left: HoldingDetail;
  right: HoldingDetail;
  estimated_overlap_pct: number;
  combined_weight_pct: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isHoldingDetail(value: unknown): value is HoldingDetail {
  return isRecord(value)
    && typeof value.symbol === 'string'
    && typeof value.name === 'string'
    && typeof value.weight_pct === 'number';
}

function asHoldingArray(value: unknown): HoldingDetail[] {
  return Array.isArray(value) ? value.filter(isHoldingDetail) : [];
}

function asOverlapPairs(value: unknown): OverlapPairDetail[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is OverlapPairDetail => (
    isRecord(item)
    && isHoldingDetail(item.left)
    && isHoldingDetail(item.right)
    && typeof item.estimated_overlap_pct === 'number'
    && typeof item.combined_weight_pct === 'number'
  ));
}

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(1)}%`;
}

function formatMoney(value: number | null | undefined, currency = 'EUR'): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function DoctorAlertDetailsModal({
  alert,
  opened,
  onClose,
  currency = 'EUR',
}: DoctorAlertDetailsModalProps) {
  const details = isRecord(alert?.details) ? alert.details : null;
  const dominantPosition = isHoldingDetail(details?.dominant_position) ? details.dominant_position : null;
  const topPositions = asHoldingArray(details?.top_positions);
  const overlapPairs = asOverlapPairs(details?.pairs);
  const overlapScore = typeof details?.overlap_score === 'number' ? details.overlap_score : null;

  return (
    <Modal opened={opened} onClose={onClose} title="Approfondimento alert" size="lg" centered>
      {!alert ? null : (
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start">
            <div>
              <Group gap="sm" mb={6}>
                <ThemeIcon color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light" radius="xl">
                  <IconAlertTriangle size={18} />
                </ThemeIcon>
                <Text size="xs" tt="uppercase" fw={800} c="dimmed">
                  Alert Doctor
                </Text>
              </Group>
              <Title order={4}>{alert.message}</Title>
            </div>
            <Badge color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
              {alert.type}
            </Badge>
          </Group>

          {alert.type === 'position_concentration' && dominantPosition && (
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="red" variant="light" radius="xl">
                  <IconBriefcase size={18} />
                </ThemeIcon>
                <Title order={5}>Posizione dominante</Title>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                <DetailStat label="Strumento" value={`${dominantPosition.symbol} · ${dominantPosition.name}`} />
                <DetailStat label="Peso" value={formatPct(dominantPosition.weight_pct)} />
                <DetailStat label="Valore" value={formatMoney(dominantPosition.market_value, currency)} />
              </SimpleGrid>

              {topPositions.length > 0 && (
                <Table withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Posizione</Table.Th>
                      <Table.Th>Peso</Table.Th>
                      <Table.Th>Valore</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {topPositions.map((position) => (
                      <Table.Tr key={`${position.symbol}-${position.name}`}>
                        <Table.Td>{position.symbol} · {position.name}</Table.Td>
                        <Table.Td>{formatPct(position.weight_pct)}</Table.Td>
                        <Table.Td>{formatMoney(position.market_value, currency)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Stack>
          )}

          {alert.type === 'etf_overlap' && overlapPairs.length > 0 && (
            <Stack gap="md">
              <Group gap="sm">
                <ThemeIcon color="orange" variant="light" radius="xl">
                  <IconArrowsShuffle size={18} />
                </ThemeIcon>
                <Title order={5}>ETF potenzialmente sovrapposti</Title>
              </Group>
              {overlapScore != null && (
                <Text c="dimmed">
                  Punteggio aggregato di sovrapposizione: <Text component="span" inherit fw={700}>{formatPct(overlapScore)}</Text>
                </Text>
              )}
              <Table withTableBorder withColumnBorders>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>ETF 1</Table.Th>
                    <Table.Th>ETF 2</Table.Th>
                    <Table.Th>Overlap stimato</Table.Th>
                    <Table.Th>Peso combinato</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {overlapPairs.map((pair) => (
                    <Table.Tr key={`${pair.left.symbol}-${pair.right.symbol}`}>
                      <Table.Td>{pair.left.symbol} ({formatPct(pair.left.weight_pct)})</Table.Td>
                      <Table.Td>{pair.right.symbol} ({formatPct(pair.right.weight_pct)})</Table.Td>
                      <Table.Td>{formatPct(pair.estimated_overlap_pct)}</Table.Td>
                      <Table.Td>{formatPct(pair.combined_weight_pct)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Stack>
          )}

          {(!details || (alert.type !== 'position_concentration' && alert.type !== 'etf_overlap')) && (
            <Text c="dimmed">
              Nessun approfondimento strutturato disponibile per questo alert.
            </Text>
          )}
        </Stack>
      )}
    </Modal>
  );
}

function DetailStat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={4}>
      <Text size="xs" tt="uppercase" fw={800} c="dimmed">
        {label}
      </Text>
      <Text fw={700}>{value}</Text>
    </Stack>
  );
}
