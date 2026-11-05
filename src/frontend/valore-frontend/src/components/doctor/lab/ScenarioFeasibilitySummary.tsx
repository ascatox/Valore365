import { Alert, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { IconCircleCheck, IconCircleX } from '@tabler/icons-react';
import type { DoctorScenarioResult } from '../../../services/api/types';
import { formatMoney, maskMoneyInText } from '../policy/policyFormat';

function Amount({ label, value, currency, privacy }: { label: string; value: number | null | undefined; currency: string; privacy: boolean }) {
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={600}>{formatMoney(value, currency, privacy)}</Text>
    </div>
  );
}

/** Feasible / infeasible (with the backend reason) and the scenario totals. Amounts are masked in Privacy Mode. */
export function ScenarioFeasibilitySummary({ result, currency, privacy }: { result: DoctorScenarioResult; currency: string; privacy: boolean }) {
  const title = result.label || 'Scenario';
  return (
    <Stack gap="xs" data-testid="scenario-feasibility">
      {result.feasible ? (
        <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />} title={`${title}: fattibile`}>
          <Text size="sm">Lo scenario rispetta i vincoli indicati.</Text>
        </Alert>
      ) : (
        <Alert color="red" variant="light" icon={<IconCircleX size={18} />} title={`${title}: non fattibile`}>
          <Text size="sm">{maskMoneyInText(result.infeasible_reason, privacy) || 'Lo scenario non rispetta i vincoli indicati.'}</Text>
        </Alert>
      )}
      {result.required_new_cash != null && (
        <Group gap={6}>
          <Text size="sm">Liquidità aggiuntiva necessaria senza vendite:</Text>
          <Text size="sm" fw={700} data-testid="required-new-cash">{formatMoney(result.required_new_cash, currency, privacy)}</Text>
        </Group>
      )}
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
        <Amount label="Valore prima" value={result.total_before} currency={currency} privacy={privacy} />
        <Amount label="Valore dopo" value={result.total_after} currency={currency} privacy={privacy} />
        <Amount label="Liquidità aggiunta" value={result.cash_in} currency={currency} privacy={privacy} />
        <Amount label="Costi ipotetici" value={result.costs?.total ?? null} currency={currency} privacy={privacy} />
      </SimpleGrid>
    </Stack>
  );
}
