import { Badge, Card, Group, Stack, Text } from '@mantine/core';
import type { TribunalArgument, TribunalRebuttal } from '../../../services/api/tribunalTypes';
import { TribunalRebuttalCard } from './TribunalRebuttalCard';
import { TribunalRichText } from './TribunalRichText';
import { STANCE_META, elementDomId, themeLabel, voiceColorVar } from './tribunalFormat';

interface TribunalArgumentCardProps {
  argument: TribunalArgument;
  /** Repliche ricevute da questo argomento, nell'ordine di arrivo. */
  rebuttals: TribunalRebuttal[];
}

/** Argomento di apertura: posizione, tema, testo con i fatti e repliche ricevute (ui-spec §3.2). */
export function TribunalArgumentCard({ argument, rebuttals }: TribunalArgumentCardProps) {
  const stance = STANCE_META[argument.stance] ?? STANCE_META.neutro;
  const StanceIcon = stance.icon;
  const domId = elementDomId(argument.id);

  return (
    <Card
      id={domId}
      tabIndex={-1}
      withBorder
      radius="md"
      padding="sm"
      data-testid="tribunal-argument"
      data-argument-id={argument.id}
      data-stance={argument.stance}
      style={{ borderLeft: `4px solid ${voiceColorVar(argument.voice)}`, overflow: 'visible', outlineOffset: 2 }}
    >
      <Stack gap="xs">
        <Group gap="xs" wrap="wrap">
          <Badge
            color={stance.color}
            variant={stance.variant}
            tt="none"
            leftSection={<StanceIcon size={12} aria-hidden="true" />}
            data-testid="tribunal-stance"
          >
            {stance.label}
          </Badge>
          <Text size="xs" c="dimmed">{themeLabel(argument.theme)}</Text>
        </Group>
        <TribunalRichText
          id={`${domId}-text`}
          template={argument.text_template}
          fallbackText={argument.text}
          factIds={argument.fact_ids}
        />
        {rebuttals.length > 0 && (
          <Stack gap={6} data-testid="tribunal-rebuttals">
            {rebuttals.map((rebuttal) => <TribunalRebuttalCard key={rebuttal.id} rebuttal={rebuttal} />)}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
