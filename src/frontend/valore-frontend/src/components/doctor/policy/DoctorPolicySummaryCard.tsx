import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAdjustmentsCheck, IconAlertTriangle, IconClockExclamation, IconStack2 } from '@tabler/icons-react';
import type { DoctorPolicyEvaluation } from '../../../services/api/types';
import { doctorErrorMessage, formatComplianceSummary, formatNearLimit, isEvaluation } from './policyFormat';

interface DoctorPolicySummaryCardProps {
  evaluation: DoctorPolicyEvaluation | null | undefined;
  isLoading: boolean;
  error: unknown;
  isAggregate: boolean;
  scopeLabel: string;
  onOpenParametri: () => void;
}

/**
 * Compliance with the user's own parameters. Deliberately separate from the
 * Doctor score: the two are never merged into one number.
 */
export function DoctorPolicySummaryCard({ evaluation, isLoading, error, isAggregate, scopeLabel, onOpenParametri }: DoctorPolicySummaryCardProps) {
  const valid = isEvaluation(evaluation) ? evaluation : null;
  const firstFail = valid?.results.find((result) => result.status === 'FAIL');
  const stale = valid?.data_quality?.status === 'stale';

  let body;
  if (isLoading) {
    body = (
      <Group gap="sm"><Loader size="sm" /><Text size="sm" c="dimmed">Verifica dei tuoi parametri…</Text></Group>
    );
  } else if (error || (evaluation != null && !valid)) {
    body = (
      <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} data-state="error">
        {`Non riusciamo a verificare i tuoi parametri ora. ${error ? doctorErrorMessage(error) : ''}`.trim()}
      </Alert>
    );
  } else if (!valid || valid.status === 'no_policy') {
    body = (
      <Stack gap="xs" data-state="no_policy">
        <Text size="sm">Non hai ancora impostato parametri per questo ambito.</Text>
        <Text size="xs" c="dimmed">Puoi partire da regole vuote o da un modello illustrativo.</Text>
        <Button variant="light" size="xs" onClick={onOpenParametri} w="fit-content">Imposta i tuoi parametri</Button>
      </Stack>
    );
  } else if (valid.status === 'empty_portfolio') {
    body = (
      <Text size="sm" data-state="empty_portfolio">
        Nessuna posizione: i parametri si verificano dopo le prime transazioni.
      </Text>
    );
  } else {
    const nearLimit = formatNearLimit(valid.summary);
    body = (
      <Stack gap={6} data-state="ready">
        <Text fw={800} size="lg" data-testid="policy-summary-text">{formatComplianceSummary(valid.summary)}</Text>
        {nearLimit && <Text size="sm" c="dimmed">{nearLimit}</Text>}
        {firstFail && <Text size="sm">{firstFail.reason}</Text>}
        {stale && (
          <Badge color="orange" variant="light" leftSection={<IconClockExclamation size={12} aria-hidden="true" />} w="fit-content">
            Quotazioni non aggiornate: alcune regole non sono verificabili
          </Badge>
        )}
        <Button variant="subtle" size="xs" onClick={onOpenParametri} w="fit-content" px={0}>Vedi i dettagli</Button>
      </Stack>
    );
  }

  return (
    <Card withBorder radius="xl" padding="lg" data-testid="policy-summary-card">
      <Stack gap="sm">
        <Group gap="sm" wrap="nowrap">
          <ThemeIcon color="blue" variant="light" radius="xl"><IconAdjustmentsCheck size={18} /></ThemeIcon>
          <div>
            <Title order={4}>I miei parametri</Title>
            <Text size="xs" c="dimmed">Verifica delle tue regole, separata dal punteggio Doctor</Text>
          </div>
        </Group>
        {isAggregate && (
          <Group gap={6} wrap="nowrap">
            <IconStack2 size={14} aria-hidden="true" />
            <Text size="xs" c="dimmed">{`${scopeLabel}: parametri indipendenti da quelli dei singoli portafogli.`}</Text>
          </Group>
        )}
        {body}
      </Stack>
    </Card>
  );
}
