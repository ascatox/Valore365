import { useId, useState } from 'react';
import { Anchor, Box, Card, Collapse, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { IconFilterOff } from '@tabler/icons-react';
import type { TribunalSessionState } from './useTribunalSession';
import { useTribunalView } from './tribunalContext';
import { DISCARDED_EXPLANATION, TRIBUNAL_VOICES, discardCodeLabel, discardedTitle, voiceName } from './tribunalFormat';

interface TribunalDiscardedNoticeProps {
  discarded: TribunalSessionState['discarded'];
}

/**
 * Affermazioni scartate dal verificatore (ui-spec §6.6): solo quante e perché, mai il testo.
 * I conteggi per voce stanno nel dettaglio espandibile, mai nell'intestazione delle voci (§7).
 */
export function TribunalDiscardedNotice({ discarded }: TribunalDiscardedNoticeProps) {
  const { voices } = useTribunalView();
  const [open, setOpen] = useState(false);
  const detailId = useId();
  if (!discarded || discarded.total <= 0) return null;

  const byCode = Object.entries(discarded.byCode).filter(([, count]) => (count ?? 0) > 0);

  return (
    <Card withBorder radius="lg" padding="md" data-testid="tribunal-discarded">
      <Stack gap="xs">
        <Group gap="xs" wrap="nowrap" align="flex-start">
          <IconFilterOff size={18} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
          <Text fw={600} size="sm" data-testid="tribunal-discarded-title">{discardedTitle(discarded.total)}</Text>
        </Group>
        <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{DISCARDED_EXPLANATION}</Text>
        <Box>
          <Anchor
            component="button"
            type="button"
            size="sm"
            aria-expanded={open}
            aria-controls={detailId}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? 'Nascondi il dettaglio' : 'Mostra il dettaglio'}
          </Anchor>
        </Box>
        <Collapse in={open} id={detailId}>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" pt="xs" data-testid="tribunal-discarded-detail">
            <Stack gap={2}>
              <Text size="xs" fw={600} c="dimmed">Per voce</Text>
              {TRIBUNAL_VOICES.map((voice) => (
                <Text key={voice.id} size="sm">{`${voiceName(voice.id, voices)}: ${discarded.byVoice[voice.id] ?? 0}`}</Text>
              ))}
              <Text size="sm">{`Sintesi: ${discarded.synthesis}`}</Text>
            </Stack>
            <Stack gap={2}>
              <Text size="xs" fw={600} c="dimmed">Per motivo</Text>
              {byCode.map(([code, count]) => (
                <Text key={code} size="sm">{`${discardCodeLabel(code)}: ${count}`}</Text>
              ))}
            </Stack>
          </SimpleGrid>
        </Collapse>
      </Stack>
    </Card>
  );
}
