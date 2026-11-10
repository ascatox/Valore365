import { Alert, Button, Card, Group, Stack, Text } from '@mantine/core';
import { IconClockPause, IconPlayerPlay, IconPlayerStop, IconRefresh, IconSettings, IconAlertCircle, IconPlugConnectedX } from '@tabler/icons-react';
import type { TribunalStatus, TribunalVoiceInfo } from '../../../services/api/tribunalTypes';
import { VoiceDot } from './TribunalVoiceColumn';

export type TribunalStateKind = 'unavailable' | 'ready' | 'error' | 'limit_reached' | 'aborted';

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  local: 'modello locale',
};

export const providerLabel = (provider: string) => PROVIDER_LABELS[provider.toLowerCase()] ?? provider;

interface TribunalStateCardProps {
  kind: TribunalStateKind;
  /** Messaggio già risolto dal codice (ui-spec §4.1). */
  message?: string | null;
  status?: TribunalStatus | null;
  voices: TribunalVoiceInfo[];
  compact?: boolean;
  /** Errore con contenuto parziale: «Seduta incompleta: non è stata salvata.» */
  incomplete?: boolean;
  onStart?: () => void;
  onRetry?: (() => void) | null;
  onOpenSettings?: () => void;
}

function UsageLines({ status }: { status?: TribunalStatus | null }) {
  if (!status) return null;
  return (
    <Stack gap={2}>
      {status.key_source === 'server' && status.limit && (
        <Text size="sm" data-testid="tribunal-daily-usage">
          {`Sedute disponibili oggi: ${status.limit.remaining} di ${status.limit.daily_limit}`}
        </Text>
      )}
      {status.provider && (
        <Text size="xs" c="dimmed" data-testid="tribunal-provider">
          {`Usa il Copilot configurato (${providerLabel(status.provider)}${status.model ? ` · ${status.model}` : ''})`}
        </Text>
      )}
    </Stack>
  );
}

/** Stati della sezione con messaggio e azioni: non disponibile, pronto, errore, limite, interrotto (ui-spec §4). */
export function TribunalStateCard({
  kind, message, status, voices, compact = false, incomplete = false, onStart, onRetry, onOpenSettings,
}: TribunalStateCardProps) {
  const startButton = onStart && (
    <Button leftSection={<IconPlayerPlay size={16} />} onClick={onStart} fullWidth={compact} data-testid="tribunal-start">
      Avvia la seduta
    </Button>
  );

  if (kind === 'ready') {
    return (
      <Card withBorder radius="lg" padding="lg" data-testid="tribunal-state-card" data-kind={kind}>
        <Stack gap="md">
          <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
            Tre voci con punti di vista dichiarati discutono il portafoglio usando solo i dati calcolati dal Doctor.
            Alla fine trovi i punti condivisi, i punti contesi e alcune domande per te. La seduta parte solo quando la avvii.
          </Text>
          <Stack gap={6} data-testid="tribunal-ready-voices">
            {voices.map((voice) => (
              <Group key={voice.id} gap={8} wrap="nowrap" align="flex-start">
                <span style={{ paddingTop: 6 }}><VoiceDot voice={voice.id} /></span>
                <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
                  <Text span fw={600} size="sm">{voice.name}</Text>
                  {` — ${voice.mandate}`}
                </Text>
              </Group>
            ))}
          </Stack>
          <UsageLines status={status} />
          <Group>{startButton}</Group>
        </Stack>
      </Card>
    );
  }

  if (kind === 'aborted') {
    return (
      <Alert color="gray" variant="light" icon={<IconPlayerStop size={18} />} data-testid="tribunal-state-card" data-kind={kind}>
        <Stack gap="sm">
          <Text size="sm">Seduta interrotta: non è stata salvata.</Text>
          <Group>{startButton}</Group>
        </Stack>
      </Alert>
    );
  }

  if (kind === 'unavailable') {
    return (
      <Alert color="yellow" variant="light" icon={<IconPlugConnectedX size={18} />} data-testid="tribunal-state-card" data-kind={kind}>
        <Stack gap="sm">
          <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{message}</Text>
          {onOpenSettings && (
            <Group>
              <Button variant="light" leftSection={<IconSettings size={16} />} onClick={onOpenSettings} fullWidth={compact}>
                Apri Impostazioni
              </Button>
            </Group>
          )}
        </Stack>
      </Alert>
    );
  }

  if (kind === 'limit_reached') {
    return (
      <Alert color="yellow" variant="light" icon={<IconClockPause size={18} />} data-testid="tribunal-state-card" data-kind={kind}>
        <Stack gap="sm">
          <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{message}</Text>
          <Group>
            <Button leftSection={<IconPlayerPlay size={16} />} disabled fullWidth={compact} data-testid="tribunal-start">
              Avvia la seduta
            </Button>
          </Group>
        </Stack>
      </Alert>
    );
  }

  return (
    <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} data-testid="tribunal-state-card" data-kind={kind}>
      <Stack gap="sm">
        <Text size="sm" style={{ overflowWrap: 'anywhere' }} data-testid="tribunal-error-message">{message}</Text>
        {incomplete && <Text size="sm" fw={600}>Seduta incompleta: non è stata salvata.</Text>}
        {onRetry && (
          <Group>
            <Button variant="light" color="red" leftSection={<IconRefresh size={16} />} onClick={onRetry} fullWidth={compact}>
              Riprova
            </Button>
          </Group>
        )}
      </Stack>
    </Alert>
  );
}
