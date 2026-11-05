import { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Loader, Modal, Stack, Text } from '@mantine/core';
import { IconHistory } from '@tabler/icons-react';
import { previewDoctorPolicy, restoreDoctorPolicyVersion } from '../../../services/api/doctor';
import type { DoctorMetricDefinition, DoctorPolicyPreviewResponse, DoctorPolicyRead, DoctorPolicyVersion } from '../../../services/api/types';
import { useDoctorPolicyVersions } from './hooks';
import { PolicyDiffList, PolicyPreviewSummary } from './PolicyPreviewSummary';
import { doctorErrorMessage, formatDateTime, isDoctorErrorCode, POLICY_VERSION_CONFLICT_MESSAGE } from './policyFormat';

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manuale',
  copilot: 'Copilot (confermata da te)',
  template: 'Da modello',
  restore: 'Ripristino',
};

interface PolicyVersionHistoryProps {
  policy: DoctorPolicyRead;
  metrics?: DoctorMetricDefinition[] | null;
  onRestored: (policy: DoctorPolicyRead) => void;
  onReload: () => void;
}

/** Versions & audit of a policy, with restore (always as a new version). */
export function PolicyVersionHistory({ policy, metrics, onRestored, onReload }: PolicyVersionHistoryProps) {
  const versionsQuery = useDoctorPolicyVersions(policy.id, policy.current_version);
  const [pending, setPending] = useState<DoctorPolicyVersion | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  // Before/after of the restore on the same data (POST /preview; its token is not used: restore takes none).
  const [restorePreview, setRestorePreview] = useState<{ loading: boolean; data: DoctorPolicyPreviewResponse | null; error: string | null }>(
    { loading: false, data: null, error: null },
  );

  const askRestore = async (version: DoctorPolicyVersion) => {
    setPending(version);
    if (!version.document) {
      setRestorePreview({ loading: false, data: null, error: 'Anteprima non disponibile per questa versione.' });
      return;
    }
    setRestorePreview({ loading: true, data: null, error: null });
    try {
      const data = await previewDoctorPolicy({
        portfolioIds: policy.scope.portfolio_ids,
        document: version.document,
        baseVersion: policy.current_version,
        source: 'manual',
      });
      setRestorePreview({ loading: false, data, error: null });
    } catch (caught) {
      if (isDoctorErrorCode(caught, 'version_conflict')) {
        setPending(null);
        setConflict(true);
      }
      setRestorePreview({ loading: false, data: null, error: `Anteprima non disponibile: ${doctorErrorMessage(caught)}` });
    }
  };

  const versions = [...(versionsQuery.data ?? [])].sort((left, right) => right.version_number - left.version_number);

  const handleRestore = async () => {
    if (!pending) return;
    setRestoring(true);
    setError(null);
    try {
      const restored = await restoreDoctorPolicyVersion(policy.id, pending.version_number, policy.current_version);
      setPending(null);
      onRestored(restored);
    } catch (caught) {
      if (isDoctorErrorCode(caught, 'version_conflict')) setConflict(true);
      else setError(doctorErrorMessage(caught));
      setPending(null);
    } finally {
      setRestoring(false);
    }
  };

  return (
    <Card withBorder radius="xl" padding="lg" data-testid="policy-version-history">
      <Stack gap="sm">
        <Group gap="xs">
          <IconHistory size={18} aria-hidden="true" />
          <Text fw={700}>Versioni e registro modifiche</Text>
        </Group>
        {conflict && (
          <Alert color="red" variant="light">
            <Group justify="space-between" wrap="wrap">
              <Text size="sm">{POLICY_VERSION_CONFLICT_MESSAGE}</Text>
              <Button size="xs" variant="light" color="red" onClick={() => { setConflict(false); onReload(); }}>Ricarica</Button>
            </Group>
          </Alert>
        )}
        {error && <Alert color="red" variant="light">{error}</Alert>}
        {versionsQuery.isLoading && <Loader size="sm" />}
        {versionsQuery.error != null && <Alert color="red" variant="light">{doctorErrorMessage(versionsQuery.error)}</Alert>}
        {versions.map((version) => {
          const current = version.version_number === policy.current_version;
          return (
            <Card key={version.version_number} withBorder radius="md" padding="sm" data-testid={`policy-version-${version.version_number}`}>
              <Stack gap={6}>
                <Group justify="space-between" wrap="wrap">
                  <Group gap="xs">
                    <Text fw={700} size="sm">{`Versione ${version.version_number}`}</Text>
                    {current && <Badge size="sm" variant="light">Attuale</Badge>}
                    <Badge size="sm" variant="outline" color="gray">{SOURCE_LABELS[version.source] ?? version.source}</Badge>
                  </Group>
                  <Text size="xs" c="dimmed">{formatDateTime(version.confirmed_at)}</Text>
                </Group>
                <PolicyDiffList diff={version.diff ?? []} metrics={metrics} />
                {!current && (
                  <Button size="xs" variant="subtle" w="fit-content" px={0} onClick={() => { void askRestore(version); }}>
                    {`Ripristina la versione ${version.version_number}`}
                  </Button>
                )}
              </Stack>
            </Card>
          );
        })}
        {!versionsQuery.isLoading && !versions.length && !versionsQuery.error && (
          <Text size="sm" c="dimmed">Nessuna versione registrata.</Text>
        )}
      </Stack>

      <Modal opened={pending != null} onClose={() => setPending(null)} title={<Text fw={700}>Ripristinare questa versione?</Text>} centered size="lg">
        <Stack gap="md">
          <Text size="sm">
            {pending && `Le regole della versione ${pending.version_number} diventeranno una nuova versione (${policy.current_version + 1}). La cronologia resta completa.`}
          </Text>
          {restorePreview.loading && (
            <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Anteprima del ripristino…</Text></Group>
          )}
          {restorePreview.data && (
            <div data-testid="restore-preview">
              <PolicyPreviewSummary preview={restorePreview.data} metrics={metrics} />
            </div>
          )}
          {restorePreview.error && <Text size="sm" c="dimmed">{restorePreview.error}</Text>}
          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={() => setPending(null)}>Annulla</Button>
            <Button onClick={handleRestore} loading={restoring} disabled={restorePreview.loading}>Conferma ripristino</Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}
