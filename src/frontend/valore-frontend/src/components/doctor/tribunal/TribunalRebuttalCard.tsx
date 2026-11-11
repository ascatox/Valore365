import { Box, Group, Text } from '@mantine/core';
import type { TribunalRebuttal } from '../../../services/api/tribunalTypes';
import { TribunalRichText } from './TribunalRichText';
import { REBUTTAL_STANCE_META, elementDomId, voiceColorVar, voiceWithPreposition } from './tribunalFormat';

interface TribunalRebuttalCardProps {
  rebuttal: TribunalRebuttal;
}

/**
 * Replica annidata sotto l'argomento a cui risponde (ui-spec §3.2): rientrata, con il bordo
 * del colore della voce che replica e `aria-describedby` verso il testo dell'argomento.
 */
export function TribunalRebuttalCard({ rebuttal }: TribunalRebuttalCardProps) {
  const stance = REBUTTAL_STANCE_META[rebuttal.stance] ?? REBUTTAL_STANCE_META.precisa;
  const StanceIcon = stance.icon;
  const title = `Replica ${voiceWithPreposition('di', rebuttal.voice)}`;

  return (
    <Box
      id={elementDomId(rebuttal.id)}
      tabIndex={-1}
      aria-describedby={`${elementDomId(rebuttal.target_argument_id)}-text`}
      aria-label={title}
      data-testid="tribunal-rebuttal"
      data-rebuttal-id={rebuttal.id}
      data-target-id={rebuttal.target_argument_id}
      data-voice={rebuttal.voice}
      ml={{ base: 'xs', sm: 'md' }}
      pl="sm"
      py={6}
      pr={6}
      style={{
        borderLeft: `3px solid ${voiceColorVar(rebuttal.voice)}`,
        background: 'var(--mantine-color-default-hover)',
        borderRadius: '0 var(--mantine-radius-sm) var(--mantine-radius-sm) 0',
        outlineOffset: 2,
      }}
    >
      <Group gap={6} wrap="wrap" mb={4}>
        <StanceIcon size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
        <Text size="xs" fw={600}>{`${title} · ${stance.label}`}</Text>
      </Group>
      <TribunalRichText template={rebuttal.text_template} fallbackText={rebuttal.text} factIds={rebuttal.fact_ids} />
    </Box>
  );
}
