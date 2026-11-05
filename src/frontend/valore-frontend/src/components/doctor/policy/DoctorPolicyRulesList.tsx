import { Alert, Card, Group, SimpleGrid, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import type { DoctorMetricDefinition, DoctorPolicyEvaluation, DoctorRuleResult } from '../../../services/api/types';
import { QualityBadge, RuleStatusBadge } from './RuleStatusBadge';
import { formatComplianceSummary, formatObserved, hasObservedRange, POINT_ESTIMATE_NOTE, formatPctValue, formatPp, formatThreshold, maskMoneyInText, ruleName, ruleStatusMeta, SEVERITY_LABELS } from './policyFormat';

export function PolicyRuleCard({ rule, metrics, onSelect }: { rule: DoctorRuleResult; metrics?: DoctorMetricDefinition[] | null; onSelect: (rule: DoctorRuleResult) => void }) {
  const name = ruleName(rule, metrics);
  const meta = ruleStatusMeta(rule.status, rule.near_limit);
  return (
    <UnstyledButton
      onClick={() => onSelect(rule)}
      aria-label={`${name}: ${meta.label}. Apri i dettagli`}
      data-testid={`rule-card-${rule.rule_id}`}
      style={{ display: 'block', width: '100%', borderRadius: 16 }}
    >
      <Card withBorder radius="lg" padding="md" style={{ borderLeft: `4px solid var(--mantine-color-${meta.color}-6)` }}>
        <Stack gap={6}>
          <Group justify="space-between" wrap="nowrap" align="flex-start">
            <Text fw={700} size="sm">{name}</Text>
            <Group gap={4} wrap="nowrap">
              <RuleStatusBadge status={rule.status} nearLimit={rule.near_limit} size="sm" />
              <IconChevronRight size={16} aria-hidden="true" />
            </Group>
          </Group>
          <SimpleGrid cols={3} spacing="xs">
            <div>
              <Text size="xs" c="dimmed">Valore attuale</Text>
              <Text size="sm" fw={700}>{formatObserved(rule)}</Text>
              {hasObservedRange(rule) && <Text size="xs" c="dimmed">{POINT_ESTIMATE_NOTE}</Text>}
            </div>
            <div>
              <Text size="xs" c="dimmed">Soglia</Text>
              <Text size="sm" fw={700}>{formatThreshold(rule)}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">Scostamento</Text>
              <Text size="sm" fw={700}>{rule.breach_amount != null ? formatPp(rule.breach_amount, rule.precision) : '—'}</Text>
            </div>
          </SimpleGrid>
          {rule.reason && <Text size="sm" c={rule.status === 'FAIL' ? 'red.8' : undefined}>{maskMoneyInText(rule.reason)}</Text>}
          <Group gap={6}>
            <Text size="xs" c="dimmed">{`Severità ${SEVERITY_LABELS[rule.severity] ?? rule.severity}`}</Text>
            {rule.coverage_pct != null && <Text size="xs" c="dimmed">{`· Copertura ${formatPctValue(rule.coverage_pct, 0)}`}</Text>}
            <QualityBadge quality={rule.quality} />
          </Group>
        </Stack>
      </Card>
    </UnstyledButton>
  );
}

interface DoctorPolicyRulesListProps {
  evaluation: DoctorPolicyEvaluation;
  metrics?: DoctorMetricDefinition[] | null;
  onSelect: (rule: DoctorRuleResult) => void;
}

/** Rules in the backend order (FAIL → UNKNOWN → near limit → PASS → …). */
export function DoctorPolicyRulesList({ evaluation, metrics, onSelect }: DoctorPolicyRulesListProps) {
  if (evaluation.status === 'empty_portfolio') {
    return (
      <Alert color="gray" variant="light" data-state="empty_portfolio">
        Nessuna posizione nell&apos;ambito: le regole non sono applicabili finché non registri le prime transazioni.
      </Alert>
    );
  }
  if (!evaluation.results.length) {
    return <Text c="dimmed" size="sm">Nessuna regola impostata. Aggiungine una dall&apos;editor.</Text>;
  }
  return (
    <Stack gap="sm">
      <Text fw={700} data-testid="rules-summary">{formatComplianceSummary(evaluation.summary)}</Text>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
        {evaluation.results.map((rule) => (
          <PolicyRuleCard key={rule.rule_id} rule={rule} metrics={metrics} onSelect={onSelect} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}
