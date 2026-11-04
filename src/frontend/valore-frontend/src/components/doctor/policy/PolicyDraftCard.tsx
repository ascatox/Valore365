import { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Stack, Text } from '@mantine/core';
import { IconCheck, IconFileDescription } from '@tabler/icons-react';
import { saveDoctorPolicy } from '../../../services/api/doctor';
import type { DoctorPolicyDraftPayload, DoctorPolicyRead } from '../../../services/api/types';
import { PolicyPreviewSummary, describeScope } from './PolicyPreviewSummary';
import { DEFAULT_POLICY_NAME } from './DoctorPolicyRuleEditor';
import { doctorErrorMessage } from './policyFormat';

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

type DraftState = 'pending' | 'saving' | 'saved' | 'cancelled';

/**
 * Copilot policy draft: shows diff + before/after and saves only when the
 * user clicks «Conferma e salva» (one-shot confirmation token).
 */
export function PolicyDraftCard({ draft, onSaved }: { draft: DoctorPolicyDraftPayload; onSaved?: (policy: DoctorPolicyRead) => void }) {
  const [state, setState] = useState<DraftState>('pending');
  const [error, setError] = useState<string | null>(null);
  const { preview } = draft;
  const canConfirm = preview.valid && Boolean(preview.confirmation_token) && Boolean(preview.normalized_document);

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setState('saving');
    setError(null);
    try {
      const saved = await saveDoctorPolicy({
        portfolioIds: draft.portfolio_ids,
        name: draft.name?.trim() || DEFAULT_POLICY_NAME,
        document: preview.normalized_document!,
        baseVersion: preview.base_version,
        confirmationToken: preview.confirmation_token!,
      });
      setState('saved');
      onSaved?.(saved);
    } catch (caught) {
      setState('pending');
      setError(doctorErrorMessage(caught));
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
          {(state === 'pending' || state === 'saving') && <Badge color="blue" variant="light">Non ancora salvata</Badge>}
        </Group>
        <PolicyPreviewSummary preview={preview} scopeLabel={describeScope(draft.portfolio_ids)} />
        {!preview.valid && (
          <Alert color="red" variant="light">
            <Stack gap={2}>
              <Text size="sm">La bozza non è valida e non può essere salvata.</Text>
              {(preview.field_errors ?? []).map((item) => <Text key={`${item.field}-${item.code}`} size="xs">{item.message}</Text>)}
            </Stack>
          </Alert>
        )}
        {error && <Alert color="red" variant="light">{error}</Alert>}
        {(state === 'pending' || state === 'saving') && (
          <Group gap="xs">
            <Button size="xs" onClick={handleConfirm} loading={state === 'saving'} disabled={!canConfirm}>Conferma e salva</Button>
            <Button size="xs" variant="default" onClick={() => setState('cancelled')} disabled={state === 'saving'}>Annulla</Button>
          </Group>
        )}
      </Stack>
    </Card>
  );
}
