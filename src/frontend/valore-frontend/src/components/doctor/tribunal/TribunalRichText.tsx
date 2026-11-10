import { Fragment, useMemo } from 'react';
import { Group, Text, type TextProps } from '@mantine/core';
import { TribunalFactChip } from './TribunalFactChip';
import { useTribunalView } from './tribunalContext';
import { maskMoneyInText, splitTemplate } from './tribunalFormat';

interface TribunalRichTextProps extends Pick<TextProps, 'size' | 'fw' | 'c'> {
  /** `text_template` o `summary_template`, con i segnaposto `{Fn}`. */
  template: string;
  /** Testo finale (`text`/`summary`), usato solo se un segnaposto punta a un fatto assente. */
  fallbackText: string;
  factIds: string[];
  /** Mostra «Fonti:» per i fatti citati che non compaiono come segnaposto. */
  showSources?: boolean;
  id?: string;
}

/**
 * Testo di un elemento della seduta con i fatti come chip selezionabili (ui-spec §3.1).
 * Nessun Markdown né HTML: React inserisce le parti come testo.
 */
export function TribunalRichText({
  template, fallbackText, factIds, showSources = true, id, size = 'sm', fw, c,
}: TribunalRichTextProps) {
  const { facts, privacy, compact } = useTribunalView();
  const parts = useMemo(() => splitTemplate(template), [template]);
  const allPresent = parts.every((part) => part.kind === 'text' || facts.has(part.id));
  const inline = new Set(parts.flatMap((part) => (part.kind === 'fact' ? [part.id] : [])));
  const extra = factIds.filter((factId) => !inline.has(factId) && facts.has(factId));

  return (
    <div>
      <Text size={size} fw={fw} c={c} id={id} style={{ overflowWrap: 'anywhere' }} data-testid="tribunal-rich-text">
        {allPresent
          ? parts.map((part, index) => (part.kind === 'text'
            ? <Fragment key={index}>{maskMoneyInText(part.value, privacy)}</Fragment>
            : <TribunalFactChip key={index} fact={facts.get(part.id)!} privacy={privacy} compact={compact} />))
          : maskMoneyInText(fallbackText, privacy)}
      </Text>
      {showSources && allPresent && extra.length > 0 && (
        <Group gap={4} mt={4} wrap="wrap" data-testid="tribunal-sources">
          <Text size="xs" c="dimmed">Fonti:</Text>
          {extra.map((factId) => (
            <TribunalFactChip key={factId} fact={facts.get(factId)!} privacy={privacy} compact={compact} small />
          ))}
        </Group>
      )}
    </div>
  );
}
