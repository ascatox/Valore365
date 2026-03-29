import { Badge, Button, Group, Popover, Stack, Text, ThemeIcon } from '@mantine/core';
import { useState } from 'react';
import { IconBook2 } from '@tabler/icons-react';

export interface GlossaryEntry {
  term: string;
  title: string;
  definition: string;
  portfolioExample: string;
}

export const DOCTOR_GLOSSARY: GlossaryEntry[] = [
  {
    term: 'diversificazione',
    title: 'Diversificazione',
    definition: 'Distribuire il capitale tra aree, strumenti o settori diversi per evitare che un solo fattore pesi troppo sul risultato finale.',
    portfolioExample: 'Se gli USA dominano il portafoglio, la diversificazione geografica e piu debole di quanto sembri.',
  },
  {
    term: 'concentrazione',
    title: 'Concentrazione',
    definition: 'Situazione in cui una singola posizione o un gruppo ristretto di posizioni pesa troppo rispetto al resto del portafoglio.',
    portfolioExample: 'Se una posizione vale quasi meta del portafoglio, il risultato dipende troppo da quel singolo strumento.',
  },
  {
    term: 'volatilita',
    title: 'Volatilita',
    definition: 'Misura di quanto il valore del portafoglio tende a oscillare nel tempo.',
    portfolioExample: 'Un livello di volatilita alto implica salite e discese piu brusche del capitale investito.',
  },
  {
    term: 'overlap',
    title: 'Overlap ETF',
    definition: 'Sovrapposizione tra strumenti che investono in parte negli stessi titoli o negli stessi segmenti di mercato.',
    portfolioExample: 'Due ETF globali o USA possono sembrare diversi, ma replicare molte delle stesse aziende.',
  },
  {
    term: 'TER',
    title: 'TER',
    definition: 'Costo annuo ricorrente del fondo o ETF, espresso in percentuale.',
    portfolioExample: 'Un TER piu alto pesa di piu se riguarda una posizione molto grande o tenuta a lungo.',
  },
];

interface GlossaryTooltipProps {
  entry: GlossaryEntry;
  highlighted?: boolean;
  onOpen?: (term: string) => void;
}

export function GlossaryTooltip({ entry, highlighted = false, onOpen }: GlossaryTooltipProps) {
  const [opened, setOpened] = useState(false);

  function handleChange(nextOpened: boolean) {
    setOpened(nextOpened);
    if (nextOpened) {
      onOpen?.(entry.term);
    }
  }

  return (
    <Popover opened={opened} onChange={handleChange} position="bottom-start" withArrow shadow="md" width={320}>
      <Popover.Target>
        <Button
          variant={highlighted ? 'filled' : 'light'}
          color={highlighted ? 'teal' : 'gray'}
          radius="xl"
          size="xs"
          onClick={() => handleChange(!opened)}
        >
          {entry.term}
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start">
            <Group gap="sm" align="flex-start">
              <ThemeIcon color="teal" variant="light" radius="xl">
                <IconBook2 size={16} />
              </ThemeIcon>
              <div>
                <Text size="xs" tt="uppercase" fw={800} c="dimmed">
                  Glossario Doctor
                </Text>
                <Text fw={700} mt={4}>{entry.title}</Text>
              </div>
            </Group>
            <Badge variant="light" color="teal" radius="xl">
              Termine chiave
            </Badge>
          </Group>
          <GlossaryRow label="Cos'e'" value={entry.definition} />
          <GlossaryRow label="Esempio sul portafoglio" value={entry.portfolioExample} />
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function GlossaryRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={4}>
      <Text size="xs" tt="uppercase" fw={800} c="dimmed">
        {label}
      </Text>
      <Text size="sm" lh={1.55}>
        {value}
      </Text>
    </Stack>
  );
}
