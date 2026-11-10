import { useId, useState, type CSSProperties } from 'react';
import { Badge, Group, Popover, Stack, Text, UnstyledButton, VisuallyHidden } from '@mantine/core';
import { IconAlertTriangle, IconCircleCheck, IconCircleDashed, IconClockExclamation } from '@tabler/icons-react';
import type { TribunalFact } from '../../../services/api/tribunalTypes';
import { BottomSheet } from '../../mobile/BottomSheet';
import { factAriaLabel, factDisplayValue, maskMoneyInText, qualityMeta, sourceLabel } from './tribunalFormat';

const QUALITY_ICONS = {
  ok: IconCircleCheck,
  partial: IconAlertTriangle,
  stale: IconClockExclamation,
  missing: IconCircleDashed,
} as const;

/** Badge della qualità del dato: icona + testo, mai solo colore (§6.4, §10). */
export function TribunalQualityBadge({ fact }: { fact: Pick<TribunalFact, 'quality' | 'citable'> }) {
  const meta = qualityMeta(fact.quality);
  const QualityIcon = QUALITY_ICONS[fact.quality] ?? IconCircleDashed;
  return (
    <Group gap={4} wrap="wrap">
      <Badge
        color={meta.color}
        variant="light"
        tt="none"
        leftSection={<QualityIcon size={12} aria-hidden="true" />}
        data-testid="tribunal-fact-quality"
      >
        {meta.label}
      </Badge>
      {!fact.citable && (
        <Badge color="gray" variant="outline" tt="none">Non citabile</Badge>
      )}
    </Group>
  );
}

interface TribunalFactDetailsProps {
  fact: TribunalFact;
  privacy: boolean;
}

/** Dettaglio di un fatto: etichetta, valore, fonte, qualità, motivo, soggetto, id (§3.1). */
export function TribunalFactDetails({ fact, privacy }: TribunalFactDetailsProps) {
  return (
    <Stack gap={6} data-testid="tribunal-fact-details" style={{ overflowWrap: 'anywhere' }}>
      <Text size="sm" fw={600}>{maskMoneyInText(fact.label, privacy)}</Text>
      <Text size="xl" fw={700} style={{ fontVariantNumeric: 'tabular-nums' }} data-testid="tribunal-fact-value">
        {factDisplayValue(fact, privacy)}
      </Text>
      <Text size="sm">
        <Text span c="dimmed" size="sm">Fonte: </Text>
        {sourceLabel(fact.source)}
      </Text>
      <TribunalQualityBadge fact={fact} />
      {fact.reason && <Text size="sm">{maskMoneyInText(fact.reason, privacy)}</Text>}
      {fact.subject && (
        <Text size="sm">
          <Text span c="dimmed" size="sm">Riferito a: </Text>
          {fact.subject}
        </Text>
      )}
      <Text size="xs" c="dimmed">{`Dato ${fact.id}`}</Text>
    </Stack>
  );
}

const chipStyle = (small: boolean): CSSProperties => ({
  display: 'inline',
  padding: small ? '0 5px' : '1px 6px',
  margin: '0 1px',
  borderRadius: 6,
  border: '1px solid var(--mantine-color-default-border)',
  background: 'var(--mantine-color-default-hover)',
  color: 'var(--mantine-color-text)',
  fontWeight: 600,
  fontSize: small ? 'var(--mantine-font-size-xs)' : 'inherit',
  lineHeight: 'inherit',
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
  textDecoration: 'underline dotted',
  textUnderlineOffset: 3,
  cursor: 'pointer',
  boxDecorationBreak: 'clone',
  WebkitBoxDecorationBreak: 'clone',
});

interface TribunalFactChipProps {
  fact: TribunalFact;
  privacy: boolean;
  /** Mobile: il dettaglio si apre in un BottomSheet invece che in un popover. */
  compact: boolean;
  /** Chip piccolo (elenco «Fonti:»). */
  small?: boolean;
}

/** Fatto citato nel testo: pulsante che apre il dettaglio (popover su desktop, bottom sheet su mobile). */
export function TribunalFactChip({ fact, privacy, compact, small = false }: TribunalFactChipProps) {
  const [opened, setOpened] = useState(false);
  const dialogTitleId = useId();
  const label = factAriaLabel(fact, privacy);
  const value = factDisplayValue(fact, privacy);

  if (compact) {
    return (
      <>
        <UnstyledButton
          type="button"
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={opened}
          data-fact-id={fact.id}
          data-testid="tribunal-fact-chip"
          style={chipStyle(small)}
          onClick={() => setOpened(true)}
        >
          {value}
        </UnstyledButton>
        <BottomSheet opened={opened} onClose={() => setOpened(false)} title="Dettaglio del dato">
          <TribunalFactDetails fact={fact} privacy={privacy} />
        </BottomSheet>
      </>
    );
  }

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      width={300}
      position="bottom"
      withArrow
      shadow="md"
      trapFocus
      returnFocus
      closeOnEscape
      closeOnClickOutside
    >
      <Popover.Target>
        <UnstyledButton
          type="button"
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={opened}
          data-fact-id={fact.id}
          data-testid="tribunal-fact-chip"
          style={chipStyle(small)}
          onClick={() => setOpened((current) => !current)}
        >
          {value}
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown aria-labelledby={dialogTitleId} maw="calc(100vw - 32px)">
        <VisuallyHidden id={dialogTitleId}>{`Dettagli del dato ${fact.id}`}</VisuallyHidden>
        <TribunalFactDetails fact={fact} privacy={privacy} />
      </Popover.Dropdown>
    </Popover>
  );
}
