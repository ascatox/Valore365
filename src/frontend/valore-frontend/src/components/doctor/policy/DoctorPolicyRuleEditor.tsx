import { useEffect, useMemo, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
} from '@mantine/core';
import { IconAlertTriangle, IconPlus, IconTrash } from '@tabler/icons-react';
import {
  previewDoctorPolicy,
  saveDoctorPolicy,
  validateDoctorPolicy,
} from '../../../services/api/doctor';
import type {
  DoctorFieldError,
  DoctorPolicyDraftPayload,
  DoctorMetricDefinition,
  DoctorPolicyDocument,
  DoctorPolicyOperator,
  DoctorPolicyPreviewResponse,
  DoctorPolicyRead,
  DoctorPolicyRule,
  DoctorPolicySeverity,
  DoctorPolicySource,
  DoctorPolicyTemplate,
} from '../../../services/api/types';
import { PolicyPreviewSummary } from './PolicyPreviewSummary';
import {
  doctorErrorMessage,
  fieldErrorsFrom,
  isDoctorErrorCode,
  metricLabel,
  OPERATOR_LABELS,
  POLICY_CONFIRMATION_INVALID_MESSAGE,
  POLICY_VERSION_CONFLICT_MESSAGE,
  SEVERITY_LABELS,
} from './policyFormat';

export const DEFAULT_POLICY_NAME = 'I miei parametri';
const MAX_RULES = 20;

interface DoctorPolicyRuleEditorProps {
  onClose: () => void;
  portfolioIds: number[];
  scopeLabel: string;
  policy: DoctorPolicyRead | null;
  metrics: DoctorMetricDefinition[];
  templates: DoctorPolicyTemplate[];
  focusRuleId?: string | null;
  /** Copilot draft loaded instead of the saved rules (still validated, previewed and confirmed here). */
  initialDraft?: DoctorPolicyDraftPayload | null;
  /**
   * Metric of a new rule to add to the saved rules, with empty thresholds (from the Tribunale).
   * If a rule on that metric already exists it is highlighted instead; nothing is saved here.
   */
  addMetricCode?: string | null;
  onSaved: (policy: DoctorPolicyRead) => void;
  onReload: () => void;
  isMobile: boolean;
}

function ruleIdFor(metricCode: string): string {
  const id = metricCode.toLowerCase().replace(/_pct$/, '').replace(/[^a-z0-9_-]/g, '-').replace(/_/g, '-');
  return (/^[a-z0-9]/.test(id) ? id : `r-${id}`).slice(0, 40);
}

function newRule(metric: DoctorMetricDefinition): DoctorPolicyRule {
  const operator: DoctorPolicyOperator = metric.operators.includes('max') ? 'max' : (metric.operators[0] ?? 'max');
  // Thresholds start empty: the user chooses them (no suggested values).
  return {
    rule_id: ruleIdFor(metric.code),
    metric_code: metric.code,
    operator,
    min_value: null,
    max_value: null,
    unit: metric.unit ?? 'pct',
    precision: metric.code === 'weighted_ter_pct' ? 2 : 1,
    severity: 'medium',
    warning_margin: metric.default_warning_margin ?? 2,
    min_coverage_pct: 80,
    max_data_age_days: 5,
    enabled: true,
    label: null,
  };
}

const toNumber = (value: number | string): number | null => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (value.trim() === '') return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
};

const cloneRules = (rules: DoctorPolicyRule[]) => rules.map((rule) => ({ ...rule }));

const templateKey = (template: DoctorPolicyTemplate) => template.template_id ?? template.code ?? template.name;

const RULE_FIELD = /^rules\[(\d+)\]\.(\w+)$/;

export function DoctorPolicyRuleEditor({
  onClose, portfolioIds, scopeLabel, policy, metrics, templates, focusRuleId, initialDraft, addMetricCode, onSaved, onReload, isMobile,
}: DoctorPolicyRuleEditorProps) {
  const baseVersion = policy?.current_version ?? null;
  const draftDocument = initialDraft?.preview.normalized_document ?? null;
  const [name, setName] = useState(initialDraft?.name?.trim() || policy?.name || DEFAULT_POLICY_NAME);
  // Rule requested from the Tribunale (computed once, at opening): added without thresholds, or
  // the existing rule on the same metric.
  const [metricRequest] = useState(() => {
    if (!addMetricCode || draftDocument) return null;
    const savedRules = policy?.document.rules ?? [];
    const existing = savedRules.find((rule) => rule.metric_code === addMetricCode);
    if (existing) return { kind: 'existing' as const, rule: existing };
    const metric = metrics.find((item) => item.code === addMetricCode);
    if (!metric) return { kind: 'unknown' as const };
    if (savedRules.length >= MAX_RULES) return { kind: 'full' as const };
    return { kind: 'added' as const, rule: newRule(metric) };
  });
  const [rules, setRules] = useState<DoctorPolicyRule[]>(() => {
    const initial = cloneRules(draftDocument?.rules ?? policy?.document.rules ?? []);
    return metricRequest?.kind === 'added' ? [...initial, { ...metricRequest.rule }] : initial;
  });
  const highlightRuleId = focusRuleId
    ?? (metricRequest?.kind === 'added' || metricRequest?.kind === 'existing' ? metricRequest.rule.rule_id : null);
  const requestedRuleId = metricRequest?.kind === 'added' || metricRequest?.kind === 'existing' ? metricRequest.rule.rule_id : null;

  useEffect(() => {
    if (!requestedRuleId) return undefined;
    // The modal renders in a portal: bring the requested rule into view once it is mounted.
    const frame = window.requestAnimationFrame(() => {
      const card = window.document.querySelector(`[data-testid="rule-editor-${requestedRuleId}"]`);
      card?.scrollIntoView?.({ block: 'nearest' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [requestedRuleId]);
  const [source, setSource] = useState<DoctorPolicySource>(draftDocument ? 'copilot' : 'manual');
  const [fieldErrors, setFieldErrors] = useState<DoctorFieldError[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState<'checking' | 'saving' | null>(null);
  const [preview, setPreview] = useState<DoctorPolicyPreviewResponse | null>(null);
  const [newMetric, setNewMetric] = useState<string | null>(null);

  const usedMetrics = useMemo(() => new Set(rules.map((rule) => rule.metric_code)), [rules]);
  const metricOptions = metrics.map((metric) => ({ value: metric.code, label: metric.label, disabled: usedMetrics.has(metric.code) }));

  const errorFor = (index: number, field: string) =>
    fieldErrors.find((item) => item.field === `rules[${index}].${field}`)?.message;
  const generalErrors = fieldErrors.filter((item) => !RULE_FIELD.test(item.field));

  const document = (): DoctorPolicyDocument => ({ schema_version: 1, rules });

  const updateRule = (index: number, patch: Partial<DoctorPolicyRule>) => {
    setSource('manual');
    setRules((current) => current.map((rule, position) => (position === index ? { ...rule, ...patch } : rule)));
  };

  const addRule = () => {
    const metric = metrics.find((item) => item.code === newMetric);
    if (!metric || usedMetrics.has(metric.code) || rules.length >= MAX_RULES) return;
    setSource('manual');
    setRules((current) => [...current, newRule(metric)]);
    setNewMetric(null);
  };

  const applyTemplate = (code: string | null) => {
    const template = templates.find((item) => templateKey(item) === code);
    if (!template) return;
    setRules(cloneRules(template.document.rules));
    setSource('template');
    setFieldErrors([]);
  };

  const handleError = (caught: unknown) => {
    if (isDoctorErrorCode(caught, 'version_conflict')) {
      setConflict(true);
      return;
    }
    const errors = fieldErrorsFrom(caught);
    if (errors.length) {
      setFieldErrors(errors);
      return;
    }
    setError(doctorErrorMessage(caught));
  };

  // validate (inline field errors) → preview (diff + before/after) → confirmation step
  const handleReview = async () => {
    setBusy('checking');
    setError(null);
    setFieldErrors([]);
    try {
      const draft = document();
      const validation = await validateDoctorPolicy(portfolioIds, draft);
      if (!validation.valid) {
        setFieldErrors(validation.field_errors ?? []);
        if (!validation.field_errors?.length) setError('La policy non è valida.');
        return;
      }
      const result = await previewDoctorPolicy({
        portfolioIds,
        document: validation.normalized_document ?? draft,
        baseVersion,
        source,
      });
      if (!result.valid || !result.confirmation_token) {
        setFieldErrors(result.field_errors ?? []);
        if (!result.field_errors?.length) setError('Anteprima non disponibile: riprova.');
        return;
      }
      setPreview(result);
    } catch (caught) {
      handleError(caught);
    } finally {
      setBusy(null);
    }
  };

  const handleConfirm = async () => {
    if (!preview?.confirmation_token) return;
    setBusy('saving');
    setError(null);
    try {
      const saved = await saveDoctorPolicy({
        portfolioIds,
        // Existing policy: its (possibly edited) name, or null to keep it; never a default that renames it.
        name: name.trim() || (policy ? null : DEFAULT_POLICY_NAME),
        document: preview.normalized_document ?? document(),
        baseVersion: preview.base_version ?? baseVersion,
        confirmationToken: preview.confirmation_token,
      });
      onSaved(saved);
    } catch (caught) {
      if (isDoctorErrorCode(caught, 'confirmation_invalid')) {
        setPreview(null);
        setError(POLICY_CONFIRMATION_INVALID_MESSAGE);
      } else {
        handleError(caught);
      }
    } finally {
      setBusy(null);
    }
  };

  const conflictAlert = conflict && (
    <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} data-testid="policy-conflict">
      <Stack gap="xs">
        <Text size="sm">{POLICY_VERSION_CONFLICT_MESSAGE}</Text>
        <Button size="xs" variant="light" color="red" w="fit-content" onClick={onReload}>Ricarica</Button>
      </Stack>
    </Alert>
  );

  return (
    <Modal
      opened
      onClose={onClose}
      size={isMobile ? '100%' : 'xl'}
      fullScreen={isMobile}
      title={<Text fw={700}>{preview ? 'Conferma le modifiche' : 'Modifica i tuoi parametri'}</Text>}
    >
      {preview ? (
        <Stack gap="md">
          {conflictAlert}
          {error && <Alert color="red" variant="light">{error}</Alert>}
          <PolicyPreviewSummary preview={preview} metrics={metrics} scopeLabel={scopeLabel} />
          <Text size="xs" c="dimmed">Nulla viene salvato finché non confermi.</Text>
          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={() => setPreview(null)} disabled={busy === 'saving'}>Torna alle modifiche</Button>
            <Button onClick={handleConfirm} loading={busy === 'saving'} disabled={conflict}>Conferma e salva</Button>
          </Group>
        </Stack>
      ) : (
        <Stack gap="md">
          <Text size="sm"><Text span fw={600}>Ambito: </Text>{scopeLabel}</Text>
          {draftDocument && (
            <Alert color="blue" variant="light" data-testid="editor-copilot-draft">
              Bozza del Copilot caricata: rivedi le regole, poi verifica e conferma. Nulla è salvato finché non confermi.
            </Alert>
          )}
          {metricRequest && addMetricCode && (
            <Alert color="blue" variant="light" data-testid="editor-tribunal-rule" data-kind={metricRequest.kind}>
              {metricRequest.kind === 'added'
                && `Nuova regola su «${metricLabel(addMetricCode, metrics)}» aggiunta senza soglie: scegli tu i valori, poi verifica e conferma. Nulla è salvato finché non confermi.`}
              {metricRequest.kind === 'existing'
                && `Hai già una regola su «${metricLabel(addMetricCode, metrics)}»: è evidenziata qui sotto. Nulla è salvato finché non confermi.`}
              {metricRequest.kind === 'full'
                && `Hai già ${MAX_RULES} regole: per aggiungerne una su «${metricLabel(addMetricCode, metrics)}» rimuovine prima un'altra.`}
              {metricRequest.kind === 'unknown'
                && 'Questa metrica non è tra quelle che puoi usare nelle regole: scegline una qui sotto.'}
            </Alert>
          )}
          {conflictAlert}
          {error && <Alert color="red" variant="light">{error}</Alert>}
          {generalErrors.length > 0 && (
            <Alert color="red" variant="light" data-testid="policy-general-errors">
              <Stack gap={2}>{generalErrors.map((item) => <Text key={`${item.field}-${item.code}`} size="sm">{item.message}</Text>)}</Stack>
            </Alert>
          )}
          <TextInput label="Nome" value={name} onChange={(event) => setName(event.currentTarget.value)} maxLength={80} />

          {templates.length > 0 && (
            <Stack gap={4}>
              <Group gap="xs" align="flex-end" wrap="wrap">
                <Select
                  label="Parti da un modello"
                  placeholder="Scegli un modello"
                  data={templates.map((template) => ({ value: templateKey(template), label: template.name }))}
                  onChange={applyTemplate}
                  value={null}
                  w={260}
                />
                <Button variant="subtle" onClick={() => { setRules([]); setSource('manual'); setFieldErrors([]); }}>
                  Parti da regole vuote
                </Button>
              </Group>
              <Text size="xs" c="dimmed">
                {templates.find((template) => template.disclaimer)?.disclaimer
                  ?? 'I modelli sono esempi illustrativi, non raccomandazioni: rivedi ogni soglia.'}
              </Text>
            </Stack>
          )}

          {rules.length === 0 && <Text size="sm" c="dimmed">Nessuna regola. Aggiungi una metrica qui sotto.</Text>}

          {rules.map((rule, index) => {
            const metric = metrics.find((item) => item.code === rule.metric_code);
            const operators = metric?.operators ?? ['min', 'max', 'range'];
            const highlighted = highlightRuleId === rule.rule_id;
            return (
              <Card
                key={`${rule.rule_id}-${index}`}
                withBorder
                radius="lg"
                padding="md"
                data-testid={`rule-editor-${rule.rule_id}`}
                style={highlighted ? { borderColor: 'var(--mantine-color-blue-5)' } : undefined}
              >
                <Stack gap="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <Text fw={700}>{metricLabel(rule.metric_code, metrics)}</Text>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={`Rimuovi regola ${metricLabel(rule.metric_code, metrics)}`}
                      onClick={() => { setSource('manual'); setRules((current) => current.filter((_, position) => position !== index)); }}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                  <Group gap="sm" align="flex-end" wrap="wrap">
                    <Stack gap={4}>
                      <Text size="sm" fw={500} id={`op-label-${index}`}>Operatore</Text>
                      <SegmentedControl
                        aria-labelledby={`op-label-${index}`}
                        value={rule.operator}
                        onChange={(value) => updateRule(index, {
                          operator: value as DoctorPolicyOperator,
                          min_value: value === 'max' ? null : rule.min_value,
                          max_value: value === 'min' ? null : rule.max_value,
                        })}
                        data={operators.map((operator) => ({ value: operator, label: OPERATOR_LABELS[operator] }))}
                      />
                      {errorFor(index, 'operator') && <Text size="xs" c="red">{errorFor(index, 'operator')}</Text>}
                    </Stack>
                    {rule.operator !== 'max' && (
                      <NumberInput
                        label="Valore minimo (%)"
                        value={rule.min_value ?? ''}
                        onChange={(value) => updateRule(index, { min_value: toNumber(value) })}
                        min={0}
                        max={100}
                        decimalScale={3}
                        decimalSeparator=","
                        error={errorFor(index, 'min_value')}
                        w={160}
                      />
                    )}
                    {rule.operator !== 'min' && (
                      <NumberInput
                        label="Valore massimo (%)"
                        value={rule.max_value ?? ''}
                        onChange={(value) => updateRule(index, { max_value: toNumber(value) })}
                        min={0}
                        max={100}
                        decimalScale={3}
                        decimalSeparator=","
                        error={errorFor(index, 'max_value')}
                        w={160}
                      />
                    )}
                  </Group>
                  <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="sm">
                    <Select
                      label="Severità"
                      value={rule.severity}
                      onChange={(value) => value && updateRule(index, { severity: value as DoctorPolicySeverity })}
                      data={(['low', 'medium', 'high'] as const).map((severity) => ({ value: severity, label: SEVERITY_LABELS[severity] }))}
                      error={errorFor(index, 'severity')}
                      allowDeselect={false}
                    />
                    <NumberInput
                      label="Margine di avviso (pp)"
                      value={rule.warning_margin ?? ''}
                      // Empty = null: the backend applies the metric default, never a silent 0.
                      onChange={(value) => updateRule(index, { warning_margin: toNumber(value) })}
                      placeholder="Predefinito della metrica"
                      min={0}
                      max={100}
                      decimalSeparator=","
                      error={errorFor(index, 'warning_margin')}
                    />
                    <NumberInput
                      label="Copertura minima (%)"
                      value={rule.min_coverage_pct ?? ''}
                      // Empty = null: the backend applies its default (80%), never a silent 0.
                      onChange={(value) => updateRule(index, { min_coverage_pct: toNumber(value) })}
                      placeholder="Predefinita (80%)"
                      min={0}
                      max={100}
                      decimalSeparator=","
                      error={errorFor(index, 'min_coverage_pct')}
                    />
                    <NumberInput
                      label="Età massima quote (giorni)"
                      value={rule.max_data_age_days ?? ''}
                      // Empty = null: the backend applies its default (5 days), never a silent 0.
                      onChange={(value) => updateRule(index, { max_data_age_days: toNumber(value) })}
                      placeholder="Predefinita (5 giorni)"
                      min={1}
                      max={365}
                      allowDecimal={false}
                      error={errorFor(index, 'max_data_age_days')}
                    />
                  </SimpleGrid>
                  <Group gap="md" wrap="wrap" align="flex-end">
                    <TextInput
                      label="Etichetta (opzionale)"
                      value={rule.label ?? ''}
                      onChange={(event) => updateRule(index, { label: event.currentTarget.value || null })}
                      maxLength={80}
                      error={errorFor(index, 'label')}
                      w={260}
                    />
                    <Switch
                      label="Regola attiva"
                      checked={rule.enabled}
                      onChange={(event) => updateRule(index, { enabled: event.currentTarget.checked })}
                    />
                  </Group>
                  {fieldErrors
                    .filter((item) => item.field === `rules[${index}]` || item.field === `rules[${index}].metric_code` || item.field === `rules[${index}].unit`)
                    .map((item) => <Text key={item.field + item.code} size="xs" c="red">{item.message}</Text>)}
                </Stack>
              </Card>
            );
          })}

          <Group gap="xs" align="flex-end" wrap="wrap">
            <Select
              label="Aggiungi una regola"
              placeholder="Scegli la metrica"
              data={metricOptions}
              value={newMetric}
              onChange={setNewMetric}
              w={280}
              disabled={rules.length >= MAX_RULES}
            />
            <Button variant="light" leftSection={<IconPlus size={16} />} onClick={addRule} disabled={!newMetric}>
              Aggiungi
            </Button>
          </Group>

          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={onClose}>Annulla</Button>
            <Button onClick={handleReview} loading={busy === 'checking'} disabled={conflict}>Verifica e anteprima</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
