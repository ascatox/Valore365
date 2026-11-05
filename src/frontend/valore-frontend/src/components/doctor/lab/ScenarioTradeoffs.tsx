import { Box, Stack, Table, Text } from '@mantine/core';
import type { DoctorScenarioResult } from '../../../services/api/types';
import { formatMoney, formatPctValue, maskMoneyInText, NOT_AVAILABLE } from '../policy/policyFormat';
import { violationKey } from './labFormat';

interface ScenarioTradeoffsProps {
  result: DoctorScenarioResult;
  currency: string;
  privacy: boolean;
  isAggregate: boolean;
  isMobile: boolean;
  /** rule_id → display name. */
  ruleNames?: Map<string, string>;
}

function refLabel(ref: DoctorScenarioResult['violations_new'][number], ruleNames?: Map<string, string>): string {
  const key = violationKey(ref);
  const name = key.label ?? (key.ruleId ? ruleNames?.get(key.ruleId) ?? key.ruleId : key.metricCode ?? NOT_AVAILABLE);
  return key.reason ? `${name}: ${key.reason}` : name;
}

/** What the scenario resolves, what it breaks, warnings and the per-position changes. */
export function ScenarioTradeoffs({ result, currency, privacy, isAggregate, isMobile, ruleNames }: ScenarioTradeoffsProps) {
  return (
    <Stack gap="sm" data-testid="scenario-tradeoffs">
      {result.violations_resolved?.length > 0 && (
        <Box>
          <Text size="sm" fw={700}>Regole che tornerebbero rispettate</Text>
          {result.violations_resolved.map((ref, index) => <Text key={index} size="sm">{`✓ ${maskMoneyInText(refLabel(ref, ruleNames), privacy)}`}</Text>)}
        </Box>
      )}
      {result.violations_new?.length > 0 && (
        <Box>
          <Text size="sm" fw={700} c="red.8">Nuove violazioni</Text>
          {result.violations_new.map((ref, index) => <Text key={index} size="sm">{`✗ ${maskMoneyInText(refLabel(ref, ruleNames), privacy)}`}</Text>)}
        </Box>
      )}
      {result.warnings?.length > 0 && (
        <Box>
          <Text size="sm" fw={700}>Avvertenze</Text>
          {result.warnings.map((warning, index) => <Text key={index} size="sm">{maskMoneyInText(warning, privacy)}</Text>)}
        </Box>
      )}
      {result.changes?.length > 0 && (
        <Box>
          <Text size="sm" fw={700} mb={4}>{isAggregate ? 'Pesi complessivi (nessun ordine per singolo conto)' : 'Variazioni per posizione'}</Text>
          {isMobile ? (
            <Stack gap={4}>
              {result.changes.map((change, index) => (
                <Text key={`${change.asset_id ?? change.symbol ?? index}`} size="sm">
                  {`${change.symbol ?? NOT_AVAILABLE}: ${formatPctValue(change.before_weight)} → ${formatPctValue(change.after_weight)}`}
                  {!isAggregate && ` (${formatMoney(change.delta_value, currency, privacy)})`}
                </Text>
              ))}
            </Stack>
          ) : (
            <Table withTableBorder fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Strumento</Table.Th>
                  <Table.Th ta="right">Peso prima</Table.Th>
                  <Table.Th ta="right">Peso dopo</Table.Th>
                  {!isAggregate && <Table.Th ta="right">Variazione</Table.Th>}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.changes.map((change, index) => (
                  <Table.Tr key={`${change.asset_id ?? change.symbol ?? index}`}>
                    <Table.Td>{change.symbol ?? NOT_AVAILABLE}</Table.Td>
                    <Table.Td ta="right">{formatPctValue(change.before_weight)}</Table.Td>
                    <Table.Td ta="right">{formatPctValue(change.after_weight)}</Table.Td>
                    {!isAggregate && <Table.Td ta="right">{formatMoney(change.delta_value, currency, privacy)}</Table.Td>}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Box>
      )}
    </Stack>
  );
}
