import { useEffect, useState } from 'react';
import { Alert, Button, Card, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconAdjustments, IconCheck, IconHistory, IconStack2 } from '@tabler/icons-react';
import type { DoctorPolicyDraftPayload, DoctorPolicyRead, DoctorRuleResult } from '../../../services/api/types';
import { DoctorPolicyRuleEditor } from './DoctorPolicyRuleEditor';
import { DoctorPolicyRulesList } from './DoctorPolicyRulesList';
import { PolicyEvidenceDrawer } from './PolicyEvidenceDrawer';
import { PolicyVersionHistory } from './PolicyVersionHistory';
import { useDoctorMetrics, useDoctorTemplates, useInvalidateDoctorPolicy, type useDoctorPolicyState } from './hooks';
import { doctorErrorMessage, formatDateTime, isEvaluation } from './policyFormat';

interface DoctorParametriSectionProps {
  portfolioIds: number[];
  isAggregate: boolean;
  scopeLabel: string;
  privacy: boolean;
  currency: string;
  isMobile: boolean;
  policyState: ReturnType<typeof useDoctorPolicyState>;
  canExplain: boolean;
  canSimulate: boolean;
  onExplain: (rule: DoctorRuleResult) => void;
  onSimulate: (rule: DoctorRuleResult) => void;
  /** Copilot draft to open in the editor («Apri nell'editor» on the draft card). */
  draftToEdit?: { id: number; draft: DoctorPolicyDraftPayload } | null;
  onDraftConsumed?: () => void;
  /**
   * New rule on one metric to open in the editor, with no thresholds (from a contested point of
   * the Tribunale). Opened once the saved rules and the metrics are loaded; still validated,
   * previewed and confirmed in the editor.
   */
  ruleToAdd?: { id: number; metricCode: string } | null;
  onRuleToAddConsumed?: () => void;
}

/** «I miei parametri»: rules with status, evidence, editor, versions & audit. */
export function DoctorParametriSection({
  portfolioIds, isAggregate, scopeLabel, privacy, currency, isMobile, policyState, canExplain, canSimulate, onExplain, onSimulate,
  draftToEdit, onDraftConsumed, ruleToAdd, onRuleToAddConsumed,
}: DoctorParametriSectionProps) {
  const { fingerprint, policyQuery, policy, evaluationQuery } = policyState;
  const metricsQuery = useDoctorMetrics();
  const templatesQuery = useDoctorTemplates();
  const invalidate = useInvalidateDoctorPolicy();
  const [editor, setEditor] = useState<{ focusRuleId: string | null; draft?: DoctorPolicyDraftPayload; addMetricCode?: string } | null>(null);
  const [selectedRule, setSelectedRule] = useState<DoctorRuleResult | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!draftToEdit) return;
    setEditor({ focusRuleId: null, draft: draftToEdit.draft });
    onDraftConsumed?.();
  }, [draftToEdit, onDraftConsumed]);

  // Wait for the saved rules (kept in the editor) and the metric definitions before opening.
  const ruleToAddReady = ruleToAdd != null && !policyQuery.isLoading && !metricsQuery.isLoading;
  useEffect(() => {
    if (!ruleToAdd || !ruleToAddReady) return;
    if (!policyQuery.error) setEditor({ focusRuleId: null, addMetricCode: ruleToAdd.metricCode });
    onRuleToAddConsumed?.();
  }, [ruleToAdd, ruleToAddReady, policyQuery.error, onRuleToAddConsumed]);

  const metrics = metricsQuery.data ?? [];
  const evaluation = isEvaluation(evaluationQuery.data) ? evaluationQuery.data : null;
  const loading = policyQuery.isLoading || evaluationQuery.isLoading;
  const error = policyQuery.error ?? evaluationQuery.error;

  const handleSaved = (saved: DoctorPolicyRead, message: string) => {
    setEditor(null);
    setNotice(message.replace('{v}', String(saved.current_version)));
    void invalidate(fingerprint);
  };

  const reload = () => {
    setEditor(null);
    void invalidate(fingerprint);
  };

  return (
    <Stack gap="lg">
      <Card withBorder radius="xl" padding="lg">
        <Stack gap="sm">
          <Group justify="space-between" wrap="wrap" align="flex-start">
            <div>
              <Group gap="xs">
                <IconAdjustments size={20} aria-hidden="true" />
                <Title order={3}>I miei parametri</Title>
              </Group>
              <Text size="sm" c="dimmed" mt={4} data-testid="policy-scope">{`Si applica a: ${scopeLabel}`}</Text>
              {policy && (
                <Text size="xs" c="dimmed">
                  {`${policy.name} · versione ${policy.current_version} · aggiornata il ${formatDateTime(policy.updated_at)}`}
                </Text>
              )}
            </div>
            <Group gap="xs">
              <Button onClick={() => setEditor({ focusRuleId: null })} disabled={metricsQuery.isLoading}>
                {policy ? 'Modifica parametri' : 'Imposta i parametri'}
              </Button>
              {policy && (
                <Button
                  variant="default"
                  leftSection={<IconHistory size={16} />}
                  onClick={() => setShowHistory((value) => !value)}
                  aria-expanded={showHistory}
                >
                  Versioni e audit
                </Button>
              )}
            </Group>
          </Group>
          {isAggregate && (
            <Alert color="gray" variant="light" icon={<IconStack2 size={16} />} data-state="aggregate_scope">
              Questi parametri valgono solo per questa combinazione di portafogli e sono indipendenti da quelli dei singoli portafogli.
            </Alert>
          )}
          <Text size="xs" c="dimmed">
            Le regole sono tue: il Doctor verifica i dati, non indica cosa comprare o vendere.
          </Text>
        </Stack>
      </Card>

      {notice && (
        <Alert color="teal" variant="light" icon={<IconCheck size={16} />} withCloseButton onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      )}

      {loading && (
        <Card withBorder radius="xl" padding="xl"><Group justify="center"><Loader /></Group></Card>
      )}

      {!loading && error != null && (
        <Alert color="red" variant="light" data-state="error">
          <Group justify="space-between" wrap="wrap">
            <Text size="sm">{`Non riusciamo a caricare i tuoi parametri. ${doctorErrorMessage(error)}`}</Text>
            <Button size="xs" variant="light" color="red" onClick={reload}>Riprova</Button>
          </Group>
        </Alert>
      )}

      {!loading && !error && evaluation?.status === 'no_policy' && (
        <Card withBorder radius="xl" padding="lg" data-state="no_policy">
          <Stack gap="sm">
            <Text fw={700}>Nessun parametro per questo ambito</Text>
            <Text size="sm" c="dimmed">
              Definisci le tue regole (per esempio un peso massimo per singola posizione) e il Doctor le verificherà sui dati del portafoglio.
            </Text>
            <Group gap="xs">
              <Button variant="light" onClick={() => setEditor({ focusRuleId: null })}>Parti da regole vuote</Button>
              {(templatesQuery.data?.length ?? 0) > 0 && (
                <Button variant="subtle" onClick={() => setEditor({ focusRuleId: null })}>Parti da un modello illustrativo</Button>
              )}
            </Group>
          </Stack>
        </Card>
      )}

      {!loading && !error && !evaluation && (
        <Alert color="gray" variant="light" data-state="unavailable">
          Verifica dei parametri non disponibile al momento (N/D).
        </Alert>
      )}

      {!loading && !error && evaluation && evaluation.status !== 'no_policy' && (
        <DoctorPolicyRulesList evaluation={evaluation} metrics={metrics} onSelect={setSelectedRule} />
      )}

      {showHistory && policy && (
        <PolicyVersionHistory
          policy={policy}
          metrics={metrics}
          onRestored={(restored) => handleSaved(restored, 'Versione ripristinata: ora è la versione {v}.')}
          onReload={reload}
        />
      )}

      <PolicyEvidenceDrawer
        rule={selectedRule}
        onClose={() => setSelectedRule(null)}
        metrics={metrics}
        privacy={privacy}
        currency={currency}
        isMobile={isMobile}
        canExplain={canExplain}
        canSimulate={canSimulate}
        onExplain={(rule) => { setSelectedRule(null); onExplain(rule); }}
        onSimulate={(rule) => { setSelectedRule(null); onSimulate(rule); }}
        onEdit={(rule) => { setSelectedRule(null); setEditor({ focusRuleId: rule.rule_id }); }}
      />

      {editor && (
        <DoctorPolicyRuleEditor
          onClose={() => setEditor(null)}
          portfolioIds={portfolioIds}
          scopeLabel={scopeLabel}
          policy={policy}
          metrics={metrics}
          templates={templatesQuery.data ?? []}
          focusRuleId={editor.focusRuleId}
          initialDraft={editor.draft ?? null}
          addMetricCode={editor.addMetricCode ?? null}
          onSaved={(saved) => handleSaved(saved, 'Parametri salvati: versione {v}.')}
          onReload={reload}
          isMobile={isMobile}
        />
      )}
    </Stack>
  );
}
