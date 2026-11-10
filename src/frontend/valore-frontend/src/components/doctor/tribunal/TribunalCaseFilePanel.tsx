import { Accordion, Box, Group, Stack, Text } from '@mantine/core';
import { IconFolder } from '@tabler/icons-react';
import type { TribunalCaseFile, TribunalFact, TribunalFactGroup } from '../../../services/api/tribunalTypes';
import { TribunalFactChip } from './TribunalFactChip';
import { useTribunalView } from './tribunalContext';
import { GROUP_LABELS, formatSessionDate, maskMoneyInText, qualityMeta, sourceLabel } from './tribunalFormat';

interface TribunalCaseFilePanelProps {
  caseFile: TribunalCaseFile;
}

/** Il fascicolo: tutti i fatti calcolati dal Doctor, per gruppo (ui-spec §2.1, §8). */
export function TribunalCaseFilePanel({ caseFile }: TribunalCaseFilePanelProps) {
  const { privacy, compact } = useTribunalView();
  const groups = new Map<TribunalFactGroup, TribunalFact[]>();
  caseFile.facts.forEach((fact) => groups.set(fact.group, [...(groups.get(fact.group) ?? []), fact]));
  const asOf = formatSessionDate(caseFile.as_of);

  return (
    <Accordion variant="contained" radius="lg" data-testid="tribunal-case-file">
      <Accordion.Item value="fascicolo">
        <Accordion.Control icon={<IconFolder size={18} aria-hidden="true" />}>
          <Text fw={600} size="sm">{`Fascicolo: ${caseFile.counts.total} dati del Doctor (${caseFile.counts.citable} citabili)`}</Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Le voci possono citare solo questi dati, calcolati dal Doctor. Tocca un valore per vederne fonte e qualità.
            </Text>
            {caseFile.notes.map((note) => (
              <Text key={note} size="sm" style={{ overflowWrap: 'anywhere' }}>{maskMoneyInText(note, privacy)}</Text>
            ))}
            {[...groups.entries()].map(([group, facts]) => (
              <Stack key={group} gap={4} data-testid={`tribunal-case-file-group-${group}`}>
                <Text size="xs" fw={700} tt="uppercase" c="dimmed">{GROUP_LABELS[group] ?? group}</Text>
                {facts.map((fact) => (
                  <Group key={fact.id} gap="xs" wrap="nowrap" align="flex-start" justify="space-between" data-testid="tribunal-case-file-fact">
                    <Box style={{ minWidth: 0, flex: 1 }}>
                      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{maskMoneyInText(fact.label, privacy)}</Text>
                      <Text size="xs" c="dimmed">
                        {`${fact.id} · ${sourceLabel(fact.source)} · ${qualityMeta(fact.quality).label}${fact.citable ? '' : ' · Non citabile'}`}
                      </Text>
                    </Box>
                    <Box style={{ flexShrink: 0 }}>
                      <TribunalFactChip fact={fact} privacy={privacy} compact={compact} />
                    </Box>
                  </Group>
                ))}
              </Stack>
            ))}
            <Text size="xs" c="dimmed">
              {`Metodologia ${caseFile.methodology_version}${asOf ? ` · quotazioni al ${asOf}` : ''}`}
            </Text>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
