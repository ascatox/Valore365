import { Alert, Badge, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { IconCircleCheck, IconCircleX } from '@tabler/icons-react';
import type { DoctorScenarioResult } from '../../../services/api/types';
import { formatMoney, formatPctValue, maskMoneyInText } from '../policy/policyFormat';
import { formatRequiredCash } from './labFormat';

/** Italian label of the backend `infeasible_code` (§8.1); unknown codes are shown as is. */
export const INFEASIBLE_CODE_LABELS: Record<string, string> = {
  insufficient_cash: 'Liquidità insufficiente',
  no_sell: 'Vincolo «nessuna vendita»',
  impossible_without_sell: 'Impossibile senza vendite',
  oversell: 'Vendita oltre la posizione',
  capacity_exceeded: 'Capacità degli strumenti superata',
  keep_equity_total: 'Quota azionaria da mantenere',
  turnover_exceeded: 'Turnover massimo superato',
  empty_portfolio: 'Portafoglio vuoto',
};

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
          <Stack gap={6}>
            {result.infeasible_code && (
              <Badge color="red" variant="outline" w="fit-content" data-testid="infeasible-code">
                {INFEASIBLE_CODE_LABELS[result.infeasible_code] ?? result.infeasible_code}
              </Badge>
            )}
            <Text size="sm">{maskMoneyInText(result.infeasible_reason, privacy) || 'Lo scenario non rispetta i vincoli indicati.'}</Text>
          </Stack>
        </Alert>
      )}
      {result.required_new_cash != null && (
        <Stack gap={2}>
          <Group gap={6}>
            <Text size="sm">Nuova liquidità totale necessaria (senza vendite):</Text>
            <Text size="sm" fw={700} data-testid="required-new-cash">{formatRequiredCash(result.required_new_cash, currency, privacy)}</Text>
          </Group>
          <Text size="xs" c="dimmed" data-testid="required-new-cash-hint">
            {`È il totale minimo di nuova liquidità da versare, costi inclusi, non un'integrazione: confrontalo con la liquidità indicata nello scenario (${formatMoney(result.cash_in, currency, privacy)}).`}
          </Text>
        </Stack>
      )}
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} spacing="xs">
        <Amount label="Valore prima" value={result.total_before} currency={currency} privacy={privacy} />
        <Amount label="Valore dopo" value={result.total_after} currency={currency} privacy={privacy} />
        <Amount label="Liquidità aggiunta" value={result.cash_in} currency={currency} privacy={privacy} />
        <Amount label="Costi ipotetici" value={result.costs?.total ?? null} currency={currency} privacy={privacy} />
        <div>
          <Text size="xs" c="dimmed">Turnover</Text>
          <Text size="sm" fw={600} data-testid="scenario-turnover">{formatPctValue(result.turnover_pct)}</Text>
        </div>
      </SimpleGrid>
    </Stack>
  );
}
