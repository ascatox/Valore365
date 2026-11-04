import { Box, Button, Drawer, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core';
import { IconFlask, IconMessageCircleQuestion, IconPencil } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import type { DoctorMetricDefinition, DoctorRuleResult } from '../../../services/api/types';
import { BottomSheet } from '../../mobile/BottomSheet';
import { QualityBadge, RuleStatusBadge } from './RuleStatusBadge';
import {
  formatDateTime,
  formatMoney,
  formatObserved,
  formatPctValue,
  formatPp,
  formatThreshold,
  NOT_AVAILABLE,
  ruleName,
  SEVERITY_LABELS,
} from './policyFormat';

interface PolicyEvidenceDrawerProps {
  rule: DoctorRuleResult | null;
  onClose: () => void;
  metrics?: DoctorMetricDefinition[] | null;
  privacy: boolean;
  currency: string;
  isMobile: boolean;
  canExplain: boolean;
  canSimulate: boolean;
  onExplain: (rule: DoctorRuleResult) => void;
  onSimulate: (rule: DoctorRuleResult) => void;
  onEdit: (rule: DoctorRuleResult) => void;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={600}>{children}</Text>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box>
      <Text size="xs" tt="uppercase" fw={800} c="dimmed" mb={4}>{title}</Text>
      {children}
    </Box>
  );
}

export function PolicyEvidenceBody({ rule, metrics, privacy, currency }: { rule: DoctorRuleResult; metrics?: DoctorMetricDefinition[] | null; privacy: boolean; currency: string }) {
  const definition = metrics?.find((metric) => metric.code === rule.metric_code);
  const evidence = rule.evidence ?? {
    source: null, denominator: null, denominator_value: null, contributors: [], notes: [], quote_as_of: null, calculated_at: null, methodology_version: null,
  };
  return (
    <Stack gap="md" data-testid="policy-evidence">
      <Group gap="xs">
        <RuleStatusBadge status={rule.status} nearLimit={rule.near_limit} />
        <QualityBadge quality={rule.quality} />
      </Group>
      {rule.reason && <Text size="sm">{rule.reason}</Text>}

      <SimpleGrid cols={2} spacing="sm">
        <Fact label="Valore attuale">{formatObserved(rule)}</Fact>
        <Fact label="Soglia">{formatThreshold(rule)}</Fact>
        <Fact label="Scostamento">{rule.breach_amount != null ? formatPp(rule.breach_amount, rule.precision) : '—'}</Fact>
        <Fact label="Severità">{SEVERITY_LABELS[rule.severity] ?? rule.severity}</Fact>
        <Fact label="Copertura dati">{formatPctValue(rule.coverage_pct, 0)}</Fact>
        <Fact label="Quote al">{formatDateTime(evidence.quote_as_of)}</Fact>
      </SimpleGrid>

      <Section title="Formula e metodologia">
        <Text size="sm">{definition?.description ?? 'Metodologia descritta dal registro metriche del Doctor.'}</Text>
        <Text size="xs" c="dimmed" mt={4}>
          {`Fonte: ${evidence.source ?? NOT_AVAILABLE} · Metodologia ${evidence.methodology_version ?? NOT_AVAILABLE} · Calcolato il ${formatDateTime(evidence.calculated_at)}`}
        </Text>
      </Section>

      <Section title="Denominatore">
        <Text size="sm">{evidence.denominator ?? definition?.denominator ?? NOT_AVAILABLE}</Text>
        <Text size="sm" fw={600} data-testid="evidence-denominator-value">{formatMoney(evidence.denominator_value, currency, privacy)}</Text>
      </Section>

      <Section title="Strumenti che contribuiscono">
        {evidence.contributors?.length ? (
          <Table withTableBorder striped fz="sm">
            <Table.Thead>
              <Table.Tr><Table.Th>Strumento</Table.Th><Table.Th>ISIN</Table.Th><Table.Th ta="right">Peso</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {evidence.contributors.map((contributor, index) => (
                <Table.Tr key={`${contributor.isin ?? contributor.symbol ?? index}`}>
                  <Table.Td>{[contributor.symbol, contributor.name].filter(Boolean).join(' · ') || NOT_AVAILABLE}</Table.Td>
                  <Table.Td>{contributor.isin ?? NOT_AVAILABLE}</Table.Td>
                  <Table.Td ta="right">{formatPctValue(contributor.weight_pct, rule.precision)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : <Text size="sm" c="dimmed">Nessuno strumento da evidenziare.</Text>}
      </Section>

      {evidence.notes?.length > 0 && (
        <Section title="Note">
          <Stack gap={2}>{evidence.notes.map((note) => <Text key={note} size="sm">{note}</Text>)}</Stack>
        </Section>
      )}
    </Stack>
  );
}

/** Evidence of one rule: drawer on desktop/tablet, bottom sheet on mobile. */
export function PolicyEvidenceDrawer({
  rule, onClose, metrics, privacy, currency, isMobile, canExplain, canSimulate, onExplain, onSimulate, onEdit,
}: PolicyEvidenceDrawerProps) {
  const title = rule ? ruleName(rule, metrics) : '';
  const content = rule && (
    <Stack gap="lg">
      <PolicyEvidenceBody rule={rule} metrics={metrics} privacy={privacy} currency={currency} />
      <Group gap="xs" wrap="wrap">
        <Button variant="light" leftSection={<IconMessageCircleQuestion size={16} />} onClick={() => onExplain(rule)} disabled={!canExplain}>
          Spiega
        </Button>
        <Button variant="light" leftSection={<IconFlask size={16} />} onClick={() => onSimulate(rule)} disabled={!canSimulate}>
          Simula
        </Button>
        <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => onEdit(rule)}>
          Modifica
        </Button>
      </Group>
    </Stack>
  );
  if (isMobile) {
    return <BottomSheet opened={rule != null} onClose={onClose} title={title}>{content}</BottomSheet>;
  }
  return (
    <Drawer opened={rule != null} onClose={onClose} position="right" size="md" title={<Text fw={700}>{title}</Text>}>
      {content}
    </Drawer>
  );
}
