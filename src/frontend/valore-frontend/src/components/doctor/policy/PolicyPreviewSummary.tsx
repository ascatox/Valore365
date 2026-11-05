import { Badge, Box, Group, List, Stack, Text } from '@mantine/core';
import type {
  DoctorMetricDefinition,
  DoctorPolicyDiffEntry,
  DoctorPolicyPreviewResponse,
  DoctorPolicyRule,
} from '../../../services/api/types';
import { formatComplianceSummary, formatThreshold, metricLabel } from './policyFormat';

const CHANGE_LABELS: Record<DoctorPolicyDiffEntry['change'], { label: string; color: string }> = {
  added: { label: 'Aggiunta', color: 'teal' },
  removed: { label: 'Rimossa', color: 'red' },
  modified: { label: 'Modificata', color: 'blue' },
};

function describeRule(rule: Partial<DoctorPolicyRule> | null | undefined): string {
  if (!rule || !rule.operator) return '—';
  const threshold = formatThreshold({
    operator: rule.operator,
    min_value: rule.min_value ?? null,
    max_value: rule.max_value ?? null,
    precision: rule.precision ?? 1,
  });
  return rule.enabled === false ? `${threshold} (disattivata)` : threshold;
}

export function PolicyDiffList({ diff, metrics }: { diff: DoctorPolicyDiffEntry[]; metrics?: DoctorMetricDefinition[] | null }) {
  if (!diff.length) return <Text size="sm" c="dimmed">Nessuna modifica rispetto alla versione attuale.</Text>;
  return (
    <List spacing={4} size="sm" listStyleType="none" data-testid="policy-diff">
      {diff.map((entry) => {
        const change = CHANGE_LABELS[entry.change];
        const name = entry.after?.label || entry.before?.label || metricLabel(entry.metric_code, metrics);
        // One entry per metric (the backend matches rules by metric_code, which is
        // unique in a document): the rule_id may change on a «modified» entry.
        return (
          <List.Item key={`${entry.metric_code}-${entry.change}`}>
            <Group gap={6} wrap="wrap">
              <Badge size="sm" variant="light" color={change.color}>{change.label}</Badge>
              <Text size="sm" fw={600}>{name}</Text>
              <Text size="sm" c="dimmed">
                {entry.change === 'added' && describeRule(entry.after)}
                {entry.change === 'removed' && describeRule(entry.before)}
                {entry.change === 'modified' && `${describeRule(entry.before)} → ${describeRule(entry.after)}`}
              </Text>
            </Group>
          </List.Item>
        );
      })}
    </List>
  );
}

/** Diff + compliance before/after (same snapshot) of a policy preview. */
export function PolicyPreviewSummary({
  preview,
  metrics,
  scopeLabel,
}: {
  preview: DoctorPolicyPreviewResponse;
  metrics?: DoctorMetricDefinition[] | null;
  scopeLabel?: string | null;
}) {
  return (
    <Stack gap="sm" data-testid="policy-preview-summary">
      {scopeLabel && <Text size="sm"><Text span fw={600}>Ambito: </Text>{scopeLabel}</Text>}
      <Box>
        <Text size="xs" tt="uppercase" fw={700} c="dimmed" mb={4}>Modifiche</Text>
        <PolicyDiffList diff={preview.diff ?? []} metrics={metrics} />
      </Box>
      <Box>
        <Text size="xs" tt="uppercase" fw={700} c="dimmed" mb={4}>Verifica sugli stessi dati</Text>
        <Text size="sm">
          <Text span fw={600}>Prima: </Text>
          {preview.evaluation_before ? formatComplianceSummary(preview.evaluation_before.summary) : 'nessun parametro impostato'}
        </Text>
        <Text size="sm">
          <Text span fw={600}>Dopo: </Text>
          {preview.evaluation_after ? formatComplianceSummary(preview.evaluation_after.summary) : 'N/D'}
        </Text>
      </Box>
    </Stack>
  );
}

/** «Portafoglio Core» or «Vista aggregata: Core, Pensione». */
export function describeScope(portfolioIds: number[], names?: Map<number, string>): string {
  const labels = portfolioIds.map((id) => names?.get(id) ?? `#${id}`);
  return portfolioIds.length > 1 ? `Vista aggregata: ${labels.join(', ')}` : `Portafoglio ${labels[0] ?? ''}`.trim();
}
