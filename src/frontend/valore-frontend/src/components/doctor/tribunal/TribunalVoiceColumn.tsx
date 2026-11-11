import { Alert, Box, Button, Group, Loader, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconArrowBackUp, IconMessageOff } from '@tabler/icons-react';
import type { TribunalArgument, TribunalRebuttal, TribunalVoiceError, TribunalVoiceInfo } from '../../../services/api/tribunalTypes';
import { TribunalArgumentCard } from './TribunalArgumentCard';
import { useTribunalView } from './tribunalContext';
import { voiceColorVar, voiceErrorMessage, voiceWithPreposition } from './tribunalFormat';

/** Dati di una voce già pronti per la resa (vedi `buildVoiceViews`). */
export interface TribunalVoiceView {
  info: TribunalVoiceInfo;
  arguments: TribunalArgument[];
  /** Repliche scritte da questa voce (compaiono sotto i bersagli, nelle altre colonne). */
  given: TribunalRebuttal[];
  errors: TribunalVoiceError[];
  /** In attesa degli argomenti di apertura (due Skeleton). */
  pending: boolean;
  /** Apertura chiusa senza argomenti ammessi. */
  noneAdmitted: boolean;
}

export function voiceArgumentCountLabel(count: number): string {
  return count === 1 ? '1 argomento' : `${count} argomenti`;
}

/** Pallino del colore della voce (sempre accanto al nome, mai da solo). */
export function VoiceDot({ voice, size = 10 }: { voice: TribunalVoiceInfo['id']; size?: number }) {
  return (
    <Box
      component="span"
      aria-hidden="true"
      style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%', background: voiceColorVar(voice), flexShrink: 0 }}
    />
  );
}

interface TribunalVoiceColumnProps {
  view: TribunalVoiceView;
  rebuttalsByTarget: ReadonlyMap<string, TribunalRebuttal[]>;
}

/** Colonna di una voce: nome, mandato, stato e argomenti (ui-spec §2, §3.2, §4). */
export function TribunalVoiceColumn({ view, rebuttalsByTarget }: TribunalVoiceColumnProps) {
  const { privacy, goTo } = useTribunalView();
  const { info } = view;
  const openingError = view.errors.find((error) => error.phase === 'apertura') ?? null;
  const laterErrors = view.errors.filter((error) => error.phase !== 'apertura');

  return (
    <Stack
      gap="sm"
      role="region"
      aria-label={info.name}
      data-testid={`tribunal-voice-${info.id}`}
      data-voice={info.id}
      style={{ minWidth: 0 }}
    >
      <Stack gap={2}>
        <Group gap={8} wrap="nowrap" align="center">
          <VoiceDot voice={info.id} size={12} />
          <Title order={4} style={{ overflowWrap: 'anywhere' }}>{info.name}</Title>
        </Group>
        <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{info.mandate}</Text>
        <Group gap={6} data-testid="tribunal-voice-status">
          {view.pending ? (
            <>
              <Loader size={12} />
              <Text size="xs" c="dimmed">In attesa degli argomenti</Text>
            </>
          ) : (
            <Text size="xs" c="dimmed">
              {openingError ? 'Non disponibile in questa seduta' : voiceArgumentCountLabel(view.arguments.length)}
            </Text>
          )}
        </Group>
      </Stack>

      {openingError && (
        <Alert color="gray" variant="light" icon={<IconMessageOff size={16} />} data-testid="tribunal-voice-error">
          {voiceErrorMessage(openingError, info.name, privacy)}
        </Alert>
      )}

      {view.pending && (
        <Stack gap="sm" data-testid="tribunal-voice-skeleton" aria-hidden="true">
          <Skeleton height={96} radius="md" />
          <Skeleton height={96} radius="md" />
        </Stack>
      )}

      {!openingError && view.noneAdmitted && (
        <Text size="sm" c="dimmed" data-testid="tribunal-voice-none">Nessun argomento ha superato la verifica.</Text>
      )}

      {view.arguments.map((argument) => (
        <TribunalArgumentCard key={argument.id} argument={argument} rebuttals={rebuttalsByTarget.get(argument.id) ?? []} />
      ))}

      {laterErrors.map((error) => (
        <Alert key={`${error.phase}-${error.code}`} color="gray" variant="light" icon={<IconMessageOff size={16} />} data-testid="tribunal-voice-error">
          {voiceErrorMessage(error, info.name, privacy)}
        </Alert>
      ))}

      {view.given.length > 0 && (
        <Stack gap={2} data-testid="tribunal-given-rebuttals">
          {view.given.map((rebuttal) => (
            <Button
              key={rebuttal.id}
              variant="subtle"
              color="gray"
              size="compact-sm"
              justify="flex-start"
              leftSection={<IconArrowBackUp size={14} aria-hidden="true" />}
              onClick={() => goTo(rebuttal.target_argument_id)}
              styles={{ label: { whiteSpace: 'normal', textAlign: 'left' }, root: { height: 'auto', minHeight: 28 } }}
            >
              {`Ha replicato ${voiceWithPreposition('a', rebuttal.target_voice)}`}
            </Button>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
