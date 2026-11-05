import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Anchor, Button, Card, Divider, Group, Stack, Text, Title } from '@mantine/core';
import { IconFlask, IconMessageCircleQuestion, IconPlus, IconStack2 } from '@tabler/icons-react';
import { usePortfolioPositions } from '../../dashboard/hooks/queries';
import { compareDoctorScenarios, previewDoctorScenario } from '../../../services/api/doctor';
import type {
  DoctorMetricDefinition,
  DoctorPolicyEvaluation,
  DoctorRuleResult,
  DoctorScenarioInput,
  DoctorScenarioRankItem,
  DoctorScenarioResult,
  DoctorScenarioSide,
} from '../../../services/api/types';
import type { PortfolioScope } from '../../../scope/portfolioScope';
import { doctorErrorMessage, isDoctorErrorCode, maskMoneyInText, ruleName, SCENARIO_DISCLAIMER } from '../policy/policyFormat';
import { emptyScenario, MAX_SCENARIOS } from './labFormat';
import { ScenarioBuilder } from './ScenarioBuilder';
import { ScenarioComparisonTable } from './ScenarioComparisonTable';
import { ScenarioFeasibilitySummary } from './ScenarioFeasibilitySummary';
import { ScenarioRanking } from './ScenarioRanking';
import { ScenarioTradeoffs } from './ScenarioTradeoffs';

export interface LabPrefill {
  id: number;
  rule: DoctorRuleResult;
}

interface DoctorLabSectionProps {
  scope: PortfolioScope;
  portfolioIds: number[];
  isAggregate: boolean;
  privacy: boolean;
  currency: string;
  isMobile: boolean;
  evaluation: DoctorPolicyEvaluation | null;
  metrics?: DoctorMetricDefinition[] | null;
  /** Set by «Simula» on a rule: the first scenario starts from it. */
  prefill?: LabPrefill | null;
  canAskCopilot: boolean;
  onAskCopilot: (prompt: string) => void;
  onSnapshotChanged: () => void;
}

interface LabResults {
  current: DoctorScenarioSide | null;
  scenarios: DoctorScenarioResult[];
  snapshotId: string | null;
  methodologyVersion: string | null;
  disclaimer: string;
  /** Backend explanation of the comparison (compare only). */
  explanation: string | null;
  /** Backend ranking of a comparison (compare only). */
  ranking: DoctorScenarioRankItem[];
  bestIndex: number | null;
}

const scenarioLetter = (index: number) => String.fromCharCode(65 + index);

/** «Laboratorio»: what-if scenarios vs the current portfolio, simulated by the backend. */
export function DoctorLabSection({
  scope, portfolioIds, isAggregate, privacy, currency, isMobile, evaluation, metrics, prefill, canAskCopilot, onAskCopilot, onSnapshotChanged,
}: DoctorLabSectionProps) {
  const { data: positions = [] } = usePortfolioPositions(scope);
  const prefillName = prefill ? ruleName(prefill.rule, metrics) : null;
  const [scenarios, setScenarios] = useState<DoctorScenarioInput[]>(() => [
    emptyScenario(prefillName ? `Rientro: ${prefillName}` : 'Scenario A'),
  ]);
  const [results, setResults] = useState<LabResults | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ruleMetric = useMemo(() => new Map((evaluation?.results ?? []).map((rule) => [rule.rule_id, rule.metric_code])), [evaluation]);
  const ruleNames = useMemo(() => new Map((evaluation?.results ?? []).map((rule) => [rule.rule_id, ruleName(rule, metrics)])), [evaluation, metrics]);

  const run = async () => {
    setRunning(true);
    setError(null);
    const base = {
      portfolio_ids: portfolioIds,
      snapshot_id: evaluation?.snapshot_id ?? null,
      policy_version: evaluation?.policy_version ?? null,
    };
    const labelled = scenarios.map((scenario, index) => ({ ...scenario, label: scenario.label.trim() || `Scenario ${scenarioLetter(index)}` }));
    try {
      if (labelled.length === 1) {
        const result = await previewDoctorScenario({ ...base, ...labelled[0] });
        setResults({
          current: result.before ?? null,
          scenarios: [{ ...result, label: result.label || labelled[0].label }],
          snapshotId: result.snapshot_id ?? null,
          methodologyVersion: result.methodology_version ?? null,
          disclaimer: result.disclaimer || SCENARIO_DISCLAIMER,
          explanation: null,
          ranking: [],
          bestIndex: null,
        });
      } else {
        const response = await compareDoctorScenarios({ ...base, scenarios: labelled });
        const list = (response.scenarios ?? []).map((result, index) => ({ ...result, label: result.label || labelled[index]?.label }));
        setResults({
          current: response.current ?? list[0]?.before ?? null,
          scenarios: list,
          snapshotId: response.snapshot_id ?? list[0]?.snapshot_id ?? null,
          methodologyVersion: response.methodology_version ?? list[0]?.methodology_version ?? null,
          disclaimer: response.disclaimer || list[0]?.disclaimer || SCENARIO_DISCLAIMER,
          explanation: response.explanation || null,
          ranking: response.ranking ?? [],
          bestIndex: response.best_index ?? null,
        });
      }
    } catch (caught) {
      if (isDoctorErrorCode(caught, 'snapshot_changed')) onSnapshotChanged();
      setError(doctorErrorMessage(caught));
    } finally {
      setRunning(false);
    }
  };

  const askCopilot = () => {
    const names = (results?.scenarios ?? []).map((scenario) => scenario.label).filter(Boolean).join(', ');
    onAskCopilot([
      `Commenta il confronto del Laboratorio Doctor tra il portafoglio attuale e ${names || 'gli scenari'}.`,
      'Usa solo i risultati della simulazione; è una simulazione teorica, nessun ordine eseguito.',
      'Spiega compromessi e dati incompleti in italiano semplice, senza consulenza personalizzata.',
    ].join('\n'));
  };

  return (
    <Stack gap="lg">
      <Card withBorder radius="xl" padding="lg">
        <Stack gap="xs">
          <Group gap="xs">
            <IconFlask size={20} aria-hidden="true" />
            <Title order={3}>Laboratorio</Title>
          </Group>
          <Text size="sm" c="dimmed">
            Confronta il portafoglio attuale con fino a {MAX_SCENARIOS} scenari ipotetici. {SCENARIO_DISCLAIMER}
          </Text>
          {isAggregate && (
            <Alert color="gray" variant="light" icon={<IconStack2 size={16} />} data-state="aggregate_scope">
              Vista aggregata: la simulazione lavora sui pesi complessivi, senza ordini per singolo conto.
            </Alert>
          )}
          {prefillName && (
            <Text size="sm" data-testid="lab-prefill">{`Simulazione avviata dalla regola «${prefillName}».`}</Text>
          )}
        </Stack>
      </Card>

      <Stack gap="sm">
        {scenarios.map((scenario, index) => (
          <ScenarioBuilder
            key={index}
            index={index}
            value={scenario}
            onChange={(next) => setScenarios((current) => current.map((item, position) => (position === index ? next : item)))}
            positions={positions}
            isAggregate={isAggregate}
            onRemove={scenarios.length > 1 ? () => setScenarios((current) => current.filter((_, position) => position !== index)) : undefined}
            hint={index === 0 && prefill ? maskMoneyInText(prefill.rule.reason, privacy) : null}
          />
        ))}
        <Group gap="xs">
          {scenarios.length < MAX_SCENARIOS && (
            <Button
              variant="default"
              leftSection={<IconPlus size={16} />}
              onClick={() => setScenarios((current) => [...current, emptyScenario(`Scenario ${scenarioLetter(current.length)}`)])}
            >
              Aggiungi scenario
            </Button>
          )}
          <Button onClick={run} loading={running} leftSection={<IconFlask size={16} />}>
            {scenarios.length > 1 ? 'Confronta scenari' : 'Simula scenario'}
          </Button>
        </Group>
      </Stack>

      {error && <Alert color="red" variant="light">{error}</Alert>}

      {results && (
        <Card withBorder radius="xl" padding="lg" data-testid="lab-results">
          <Stack gap="md">
            <Title order={4}>Risultati</Title>
            <Text size="sm" fw={600} data-testid="lab-disclaimer">{results.disclaimer}</Text>
            {results.scenarios.map((result, index) => (
              <ScenarioFeasibilitySummary key={`${result.label}-${index}`} result={result} currency={currency} privacy={privacy} />
            ))}
            <ScenarioComparisonTable current={results.current} scenarios={results.scenarios} isMobile={isMobile} ruleMetric={ruleMetric} privacy={privacy} />
            <ScenarioRanking
              ranking={results.ranking}
              bestIndex={results.bestIndex}
              names={results.scenarios.map((result, index) => result.label || `Scenario ${scenarioLetter(index)}`)}
              currency={currency}
              privacy={privacy}
              isMobile={isMobile}
            />
            {results.explanation && (
              <Text size="sm" data-testid="lab-explanation">{maskMoneyInText(results.explanation, privacy)}</Text>
            )}
            {results.scenarios.map((result, index) => (
              <Stack key={`tradeoffs-${index}`} gap={4}>
                <Divider label={result.label || `Scenario ${scenarioLetter(index)}`} labelPosition="left" />
                <ScenarioTradeoffs result={result} currency={currency} privacy={privacy} isAggregate={isAggregate} isMobile={isMobile} ruleNames={ruleNames} />
              </Stack>
            ))}
            <Text size="xs" c="dimmed">
              {`Snapshot ${results.snapshotId ?? 'N/D'} · metodologia ${results.methodologyVersion ?? 'N/D'}: con gli stessi dati la simulazione dà lo stesso risultato.`}
            </Text>
            <Group gap="sm" wrap="wrap">
              <Button
                variant="light"
                leftSection={<IconMessageCircleQuestion size={16} />}
                onClick={askCopilot}
                disabled={!canAskCopilot}
              >
                Chiedi al Copilot di commentare
              </Button>
              <Anchor component={Link} to="/portfolio" size="sm">Traduci in ordini nella pagina Portfolio</Anchor>
            </Group>
          </Stack>
        </Card>
      )}

      <Text size="xs" c="dimmed">
        Domande su capitale, rendita o pensione? <Anchor component={Link} to="/fire" size="xs">Vai alla pagina FIRE</Anchor>.
      </Text>
    </Stack>
  );
}
