import { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Stack, Text } from '@mantine/core';
import { IconCheck, IconFileDescription, IconPencil, IconRefresh } from '@tabler/icons-react';
import { getDoctorPolicy, previewDoctorPolicy, saveDoctorPolicy } from '../../../services/api/doctor';
import type { DoctorPolicyDraftPayload, DoctorPolicyPreviewResponse, DoctorPolicyRead } from '../../../services/api/types';
import { PolicyPreviewSummary, describeScope } from './PolicyPreviewSummary';
import { doctorErrorMessage, isDoctorErrorCode, maskMoneyInText, POLICY_CONFIRMATION_INVALID_MESSAGE } from './policyFormat';

export const DRAFT_VERSION_CONFLICT_MESSAGE =
  "I parametri sono stati modificati dopo questa bozza: rigenera l'anteprima sulla versione attuale e conferma di nuovo.";

/** Parses the `policy_draft` SSE content (JSON string or object); null when malformed. */
export function parsePolicyDraft(content: unknown): DoctorPolicyDraftPayload | null {
  let value = content;
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  // The contract allows the preview fields at top level next to portfolio_ids.
  const preview = (raw.preview && typeof raw.preview === 'object' ? raw.preview : raw) as DoctorPolicyDraftPayload['preview'];
  const ids = Array.isArray(raw.portfolio_ids) ? raw.portfolio_ids.filter((id): id is number => typeof id === 'number') : [];
  if (!ids.length || !preview || !Array.isArray(preview.diff)) return null;
  return { portfolio_ids: ids, preview, name: typeof raw.name === 'string' ? raw.name : null };
}

type DraftState = 'pending' | 'saving' | 'regenerating' | 'saved' | 'cancelled';

interface PolicyDraftCardProps {
  draft: DoctorPolicyDraftPayload;
  onSaved?: (policy: DoctorPolicyRead) => void;
  /** Portfolio id → name, to show the scope by name instead of `#id`. */
  portfolioNames?: Map<number, string>;
  /** Opens «I miei parametri» with this draft loaded in the editor (only when the draft matches the page scope). */
  onOpenInEditor?: (draft: DoctorPolicyDraftPayload) => void;
}

/**
 * Copilot policy draft: shows diff + before/after and saves only when the
 * user clicks «Conferma e salva» (one-shot confirmation token). After a 409
 * the preview can be regenerated on the current version (new token), and
 * saving still needs a new explicit click.
 */
export function PolicyDraftCard({ draft, onSaved, portfolioNames, onOpenInEditor }: PolicyDraftCardProps) {
  const [state, setState] = useState<DraftState>('pending');
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DoctorPolicyPreviewResponse>(draft.preview);
  const [needsRegeneration, setNeedsRegeneration] = useState(false);
  const canConfirm = !needsRegeneration && preview.valid && Boolean(preview.confirmation_token) && Boolean(preview.normalized_document);
  const active = state === 'pending' || state === 'saving' || state === 'regenerating';

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setState('saving');
    setError(null);
    try {
      const saved = await saveDoctorPolicy({
        portfolioIds: draft.portfolio_ids,
        // No name in the draft → null: the backend keeps the existing policy name.
        name: draft.name?.trim() || null,
        document: preview.normalized_document!,
        baseVersion: preview.base_version,
        confirmationToken: preview.confirmation_token!,
      });
      setState('saved');
      onSaved?.(saved);
    } catch (caught) {
      setState('pending');
      if (isDoctorErrorCode(caught, 'version_conflict')) {
        setNeedsRegeneration(true);
        setError(DRAFT_VERSION_CONFLICT_MESSAGE);
      } else if (isDoctorErrorCode(caught, 'confirmation_invalid')) {
        setNeedsRegeneration(true);
        setError(POLICY_CONFIRMATION_INVALID_MESSAGE);
      } else {
        setError(doctorErrorMessage(caught));
      }
    }
  };

  // New preview of the same document on the current version: new token, nothing saved.
  const handleRegenerate = async () => {
    if (!preview.normalized_document) return;
    setState('regenerating');
    setError(null);
    try {
      const current = await getDoctorPolicy(draft.portfolio_ids);
      const next = await previewDoctorPolicy({
        portfolioIds: draft.portfolio_ids,
        document: preview.normalized_document,
        baseVersion: current?.current_version ?? null,
        source: 'copilot',
      });
      setPreview(next);
      setNeedsRegeneration(false);
    } catch (caught) {
      setError(doctorErrorMessage(caught));
    } finally {
      setState('pending');
    }
  };

  return (
    <Card withBorder radius="lg" padding="md" data-testid="policy-draft-card">
      <Stack gap="sm">
        <Group gap="xs" justify="space-between" wrap="wrap">
          <Group gap="xs">
            <IconFileDescription size={18} aria-hidden="true" />
            <Text fw={700} size="sm">Bozza di parametri</Text>
          </Group>
          {state === 'saved' && <Badge color="teal" leftSection={<IconCheck size={12} aria-hidden="true" />}>Salvata</Badge>}
          {state === 'cancelled' && <Badge color="gray">Annullata</Badge>}
          {active && <Badge color="blue" variant="light">Non ancora salvata</Badge>}
        </Group>
        <PolicyPreviewSummary preview={preview} scopeLabel={describeScope(draft.portfolio_ids, portfolioNames)} />
        {!preview.valid && (
          <Alert color="red" variant="light">
            <Stack gap={2}>
              <Text size="sm">La bozza non è valida e non può essere salvata.</Text>
              {(preview.field_errors ?? []).map((item) => <Text key={`${item.field}-${item.code}`} size="xs">{maskMoneyInText(item.message)}</Text>)}
            </Stack>
          </Alert>
        )}
        {error && (
          <Alert color="red" variant="light" data-testid="policy-draft-error">
            <Stack gap="xs">
              <Text size="sm">{maskMoneyInText(error)}</Text>
              {needsRegeneration && (
                <Button
                  size="xs"
                  variant="light"
                  color="red"
                  w="fit-content"
                  leftSection={<IconRefresh size={14} />}
                  onClick={handleRegenerate}
                  loading={state === 'regenerating'}
                >
                  Rigenera anteprima
                </Button>
              )}
            </Stack>
          </Alert>
        )}
        {active && (
          <Group gap="xs" wrap="wrap">
            <Button size="xs" onClick={handleConfirm} loading={state === 'saving'} disabled={!canConfirm || state === 'regenerating'}>Conferma e salva</Button>
            {onOpenInEditor && preview.normalized_document && (
              <Button
                size="xs"
                variant="light"
                leftSection={<IconPencil size={14} />}
                onClick={() => onOpenInEditor({ ...draft, preview })}
                disabled={state !== 'pending'}
              >
                Apri nell&apos;editor
              </Button>
            )}
            <Button size="xs" variant="default" onClick={() => setState('cancelled')} disabled={state !== 'pending'}>Annulla</Button>
          </Group>
        )}
      </Stack>
    </Card>
  );
}
