import type { ReactNode } from 'react';
import { Anchor, Badge, Box, Card, Group, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core';
import type { TribunalContestedPoint, TribunalSynthesis as TribunalSynthesisData, TribunalVoiceId } from '../../../services/api/tribunalTypes';
import { TribunalRichText } from './TribunalRichText';
import { useTribunalView } from './tribunalContext';
import { maskMoneyInText, voiceMeta, voiceName, voiceOfElementId } from './tribunalFormat';

interface TribunalSynthesisProps {
  synthesis: TribunalSynthesisData | null;
  /** Sintesi in arrivo (fase in corso): Skeleton. */
  pending?: boolean;
  /** Slot di TASK-70 per le azioni di un punto conteso. */
  renderContestedActions?: (point: TribunalContestedPoint) => ReactNode;
}

function ArgumentLinks({ ids }: { ids: string[] }) {
  const { voices, goTo } = useTribunalView();
  const links = ids.flatMap((id) => {
    const voice = voiceOfElementId(id);
    return voice ? [{ id, label: `${voiceName(voice, voices)} · ${id.startsWith('R-') ? 'replica' : 'argomento'}` }] : [];
  });
  if (links.length === 0) return null;
  return (
    <Group gap={4} wrap="wrap" data-testid="tribunal-argument-links">
      <Text size="xs" c="dimmed">Vedi:</Text>
      {links.map((link, index) => (
        <Group key={link.id} gap={0} wrap="nowrap">
          <Anchor component="button" type="button" size="xs" onClick={() => goTo(link.id)}>
            {link.label}
          </Anchor>
          {index < links.length - 1 && <Text span size="xs" c="dimmed" aria-hidden="true">;</Text>}
        </Group>
      ))}
    </Group>
  );
}

function VoiceBadges({ voices: ids }: { voices: TribunalVoiceId[] }) {
  const { voices } = useTribunalView();
  return (
    <Group gap={4} wrap="wrap">
      {ids.map((id) => (
        <Badge key={id} color={voiceMeta(id).color} variant="light" tt="none" data-testid="tribunal-side-voice">
          {voiceName(id, voices)}
        </Badge>
      ))}
    </Group>
  );
}

/**
 * Sintesi della seduta (ui-spec §3.3): punti condivisi, punti contesi con i due lati di uguale
 * peso, domande per te. Nessun vincitore, nessun punteggio, nessun «esito» (§7).
 */
export function TribunalSynthesis({ synthesis, pending = false, renderContestedActions }: TribunalSynthesisProps) {
  const { voices, privacy } = useTribunalView();

  if (!synthesis) {
    if (!pending) return null;
    return (
      <Card withBorder radius="lg" padding="lg" data-testid="tribunal-synthesis" data-pending="true">
        <Stack gap="sm" aria-hidden="true">
          <Skeleton height={20} width="40%" />
          <Skeleton height={60} />
          <Skeleton height={60} />
        </Stack>
      </Card>
    );
  }

  const isEmpty = synthesis.shared_points.length === 0 && synthesis.contested_points.length === 0
    && synthesis.open_questions.length === 0;

  return (
    <Card withBorder radius="lg" padding="lg" data-testid="tribunal-synthesis">
      <Stack gap="lg">
        <Title order={3}>Sintesi della seduta</Title>
        {isEmpty && (
          <Text size="sm" data-testid="tribunal-synthesis-empty">
            La sintesi non ha prodotto punti verificabili. Gli argomenti delle voci restano consultabili qui sopra.
          </Text>
        )}

        {synthesis.shared_points.length > 0 && (
          <Stack gap="sm" data-testid="tribunal-shared-points">
            <Title order={4}>Punti condivisi</Title>
            {synthesis.shared_points.map((point) => (
              <Box key={point.id} data-testid="tribunal-shared-point">
                <TribunalRichText template={point.text_template} fallbackText={point.text} factIds={point.fact_ids} />
                <Group gap={6} mt={6} wrap="wrap">
                  <Badge color="gray" variant="light" tt="none" style={{ maxWidth: '100%', height: 'auto', whiteSpace: 'normal' }}>
                    {`Concordano: ${point.voices.map((id) => voiceName(id, voices)).join(', ')}`}
                  </Badge>
                </Group>
                <Box mt={4}><ArgumentLinks ids={point.argument_ids} /></Box>
              </Box>
            ))}
          </Stack>
        )}

        {synthesis.contested_points.length > 0 && (
          <Stack gap="sm" data-testid="tribunal-contested-points">
            <Title order={4}>Punti contesi</Title>
            {synthesis.contested_points.map((point) => (
              <Card key={point.id} withBorder radius="md" padding="md" data-testid="tribunal-contested-point" data-point-id={point.id}>
                <Stack gap="sm">
                  <TribunalRichText template={point.text_template} fallbackText={point.text} factIds={point.fact_ids} fw={600} />
                  <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                    {point.sides.map((side, index) => (
                      <Box
                        key={index}
                        p="sm"
                        data-testid="tribunal-contested-side"
                        style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 'var(--mantine-radius-sm)', minWidth: 0 }}
                      >
                        <Stack gap={6}>
                          <VoiceBadges voices={side.voices} />
                          <TribunalRichText template={side.summary_template} fallbackText={side.summary} factIds={side.fact_ids} />
                          <ArgumentLinks ids={side.argument_ids} />
                        </Stack>
                      </Box>
                    ))}
                  </SimpleGrid>
                  {renderContestedActions?.(point)}
                </Stack>
              </Card>
            ))}
          </Stack>
        )}

        {synthesis.open_questions.length > 0 && (
          <Stack gap={4} data-testid="tribunal-open-questions">
            <Title order={4}>Domande per te</Title>
            <Box component="ol" m={0} pl="lg">
              {synthesis.open_questions.map((question) => (
                <Text key={question.id} component="li" size="sm" mb={4} style={{ overflowWrap: 'anywhere' }}>
                  {maskMoneyInText(question.text, privacy)}
                </Text>
              ))}
            </Box>
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
