import { Badge, Card, Group, Stack, Table, Text } from '@mantine/core';
import { IconArrowDownRight, IconArrowUpRight, IconHelpCircle } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import type { DoctorScenarioResult, DoctorScenarioSide } from '../../../services/api/types';
import { formatComplianceSummary, formatPctValue, maskMoneyInText, metricLabel, NOT_AVAILABLE } from '../policy/policyFormat';
import { formatMetric, isIncomplete, sideMetric, sideMetricCodes, touchedMetrics } from './labFormat';

interface Row {
  key: string;
  group: string;
  label: string;
}

const VOLATILITY_ROW = 'volatility';

const BASE_ROWS: Row[] = [
  { key: 'compliance', group: 'Conformità', label: 'Regole' },
  { key: 'max_single_position_pct', group: 'Concentrazione', label: metricLabel('max_single_position_pct') },
  { key: 'top3_positions_pct', group: 'Concentrazione', label: metricLabel('top3_positions_pct') },
  { key: 'equity_weight_pct', group: 'Asset allocation', label: metricLabel('equity_weight_pct') },
  { key: 'bond_weight_pct', group: 'Asset allocation', label: metricLabel('bond_weight_pct') },
  { key: 'gold_weight_pct', group: 'Asset allocation', label: metricLabel('gold_weight_pct') },
  { key: 'usa_exposure_pct', group: 'Geografia', label: metricLabel('usa_exposure_pct') },
  { key: 'weighted_ter_pct', group: 'Costi', label: metricLabel('weighted_ter_pct') },
  { key: 'etf_overlap_pct', group: 'Overlap', label: metricLabel('etf_overlap_pct') },
  { key: VOLATILITY_ROW, group: 'Rischio', label: 'Volatilità' },
];

type Trend = 'better' | 'worse' | 'incomplete' | null;

interface Cell {
  text: string;
  trend: Trend;
  /** Backend explanation shown under the value (e.g. why volatility is N/D). */
  note?: string | null;
}

/** Volatility exactly as the backend gives it: never estimated here (always N/D + reason in the MVP). */
function volatilityCell(side: DoctorScenarioSide | null | undefined, privacy?: boolean): Cell {
  const volatility = side?.volatility;
  if (volatility?.value != null && Number.isFinite(volatility.value)) return { text: formatPctValue(volatility.value), trend: null };
  return { text: NOT_AVAILABLE, trend: null, note: maskMoneyInText(volatility?.reason ?? null, privacy) };
}

function rowsFor(current: DoctorScenarioSide | null, scenarios: DoctorScenarioResult[]): Row[] {
  // Stress rows only when the backend supports them for this snapshot.
  const codes = new Set([...sideMetricCodes(current), ...scenarios.flatMap((scenario) => sideMetricCodes(scenario.after))]);
  const stress = [...codes].filter((code) => code.startsWith('stress')).map((code) => ({ key: code, group: 'Stress', label: metricLabel(code) }));
  return [...BASE_ROWS, ...stress];
}

function currentCell(row: Row, current: DoctorScenarioSide | null, privacy?: boolean): Cell {
  if (row.key === 'compliance') return { text: current?.evaluation_summary ? formatComplianceSummary(current.evaluation_summary) : NOT_AVAILABLE, trend: null };
  if (row.key === VOLATILITY_ROW) return volatilityCell(current, privacy);
  const metric = sideMetric(current, row.key);
  return { text: formatMetric(metric), trend: isIncomplete(metric) ? 'incomplete' : null };
}

function scenarioCell(row: Row, current: DoctorScenarioSide | null, scenario: DoctorScenarioResult, ruleMetric: Map<string, string>, privacy?: boolean): Cell {
  const after = scenario.feasible ? scenario.after : null;
  if (!after) return { text: NOT_AVAILABLE, trend: 'incomplete' };
  if (row.key === VOLATILITY_ROW) return volatilityCell(after, privacy);
  if (row.key === 'compliance') {
    const summary = after.evaluation_summary;
    if (!summary) return { text: NOT_AVAILABLE, trend: 'incomplete' };
    const before = current?.evaluation_summary;
    let trend: Trend = null;
    if (before && summary.failed < before.failed) trend = 'better';
    else if (before && summary.failed > before.failed) trend = 'worse';
    return { text: formatComplianceSummary(summary), trend };
  }
  const metric = sideMetric(after, row.key);
  if (isIncomplete(metric)) return { text: formatMetric(metric), trend: 'incomplete' };
  const { resolved, created } = touchedMetrics(scenario, ruleMetric);
  const trend: Trend = created.has(row.key) ? 'worse' : resolved.has(row.key) ? 'better' : null;
  return { text: formatMetric(metric), trend };
}

function TrendMark({ trend }: { trend: Trend }): ReactNode {
  if (trend === 'better') return <Badge size="xs" color="teal" variant="light" leftSection={<IconArrowUpRight size={10} aria-hidden="true" />}>Migliora</Badge>;
  if (trend === 'worse') return <Badge size="xs" color="red" variant="light" leftSection={<IconArrowDownRight size={10} aria-hidden="true" />}>Peggiora</Badge>;
  if (trend === 'incomplete') return <Badge size="xs" color="gray" variant="outline" leftSection={<IconHelpCircle size={10} aria-hidden="true" />}>Dati incompleti</Badge>;
  return null;
}

function CellView({ cell }: { cell: Cell }) {
  return (
    <Stack gap={2}>
      <Text size="sm" fw={600}>{cell.text}</Text>
      {cell.note && <Text size="xs" c="dimmed">{cell.note}</Text>}
      <TrendMark trend={cell.trend} />
    </Stack>
  );
}

interface ScenarioComparisonTableProps {
  current: DoctorScenarioSide | null;
  scenarios: DoctorScenarioResult[];
  isMobile: boolean;
  /** rule_id → metric_code of the current evaluation (for violation refs given by rule id). */
  ruleMetric?: Map<string, string>;
  /** Privacy Mode (masks amounts in backend notes); defaults to the stored flag. */
  privacy?: boolean;
}

/** «Attuale» vs scenarios: table on desktop, stacked cards on mobile. */
export function ScenarioComparisonTable({ current, scenarios, isMobile, ruleMetric = new Map(), privacy }: ScenarioComparisonTableProps) {
  const rows = rowsFor(current, scenarios);
  const names = scenarios.map((scenario, index) => scenario.label || `Scenario ${String.fromCharCode(65 + index)}`);

  if (isMobile) {
    return (
      <Stack gap="sm" data-testid="scenario-comparison-cards">
        {scenarios.map((scenario, index) => (
          <Card key={names[index]} withBorder radius="lg" padding="md">
            <Text fw={700} mb="xs">{names[index]}</Text>
            <Stack gap="xs">
              {rows.map((row) => {
                const now = currentCell(row, current, privacy);
                const next = scenarioCell(row, current, scenario, ruleMetric, privacy);
                return (
                  <div key={row.key}>
                    <Text size="xs" c="dimmed">{`${row.group} · ${row.label}`}</Text>
                    <Group gap={6} wrap="wrap" align="flex-start">
                      <Text size="sm">{`Attuale: ${now.text}`}</Text>
                      <Text size="sm" aria-hidden="true">→</Text>
                      <CellView cell={next} />
                    </Group>
                    {now.note && now.note !== next.note && <Text size="xs" c="dimmed">{`Attuale: ${now.note}`}</Text>}
                  </div>
                );
              })}
            </Stack>
          </Card>
        ))}
      </Stack>
    );
  }

  return (
    <Table.ScrollContainer minWidth={560}>
      <Table withTableBorder withColumnBorders data-testid="scenario-comparison-table">
        <Table.Caption>Confronto tra il portafoglio attuale e gli scenari simulati</Table.Caption>
        <Table.Thead>
          <Table.Tr>
            <Table.Th scope="col">Metrica</Table.Th>
            <Table.Th scope="col">Attuale</Table.Th>
            {names.map((name) => <Table.Th key={name} scope="col">{name}</Table.Th>)}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.key}>
              <Table.Th scope="row">
                <Text size="xs" c="dimmed">{row.group}</Text>
                <Text size="sm" fw={500}>{row.label}</Text>
              </Table.Th>
              <Table.Td><CellView cell={currentCell(row, current, privacy)} /></Table.Td>
              {scenarios.map((scenario, index) => (
                <Table.Td key={names[index]}><CellView cell={scenarioCell(row, current, scenario, ruleMetric, privacy)} /></Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
