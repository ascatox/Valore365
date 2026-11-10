import { useId, useState } from 'react';
import { Alert, Anchor, Text } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { DISCLAIMER_FIRST, DISCLAIMER_LAST, DISCLAIMER_MIDDLE } from './tribunalFormat';

interface TribunalDisclaimerProps {
  /** Su mobile la parte centrale si espande con «Leggi tutto» (resta comunque nel DOM). */
  compact?: boolean;
}

/** Avvertenza del Tribunale (ui-spec §5): sempre visibile, non chiudibile. */
export function TribunalDisclaimer({ compact = false }: TribunalDisclaimerProps) {
  const [expanded, setExpanded] = useState(false);
  const middleId = useId();
  const collapsed = compact && !expanded;

  return (
    <Alert
      variant="light"
      color="gray"
      icon={<IconInfoCircle size={18} aria-hidden="true" />}
      data-testid="tribunal-disclaimer"
      styles={{ message: { overflowWrap: 'anywhere' } }}
    >
      <Text size="sm" component="p" m={0}>
        {DISCLAIMER_FIRST}{' '}
        <span id={middleId} style={collapsed ? { display: 'none' } : undefined}>{DISCLAIMER_MIDDLE} </span>
        {DISCLAIMER_LAST}
        {compact && (
          <>
            {' '}
            <Anchor
              component="button"
              type="button"
              size="sm"
              aria-expanded={expanded}
              aria-controls={middleId}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? 'Mostra meno' : 'Leggi tutto'}
            </Anchor>
          </>
        )}
      </Text>
    </Alert>
  );
}
