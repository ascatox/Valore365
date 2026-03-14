import { Card, Group, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconLayoutList, IconClipboardCheck, IconAdjustments } from '@tabler/icons-react';
import type { CreatorMethod } from './types';

interface CreatorMethodPickerProps {
  onPick: (method: CreatorMethod) => void;
}

const METHODS: { method: CreatorMethod; icon: typeof IconLayoutList; color: string; title: string; description: string }[] = [
  {
    method: 'model',
    icon: IconLayoutList,
    color: 'blue',
    title: 'Modello pronto',
    description: 'Scegli da una libreria di portafogli collaudati: All Weather, Golden Butterfly, 60/40 e altri.',
  },
  {
    method: 'profile',
    icon: IconClipboardCheck,
    color: 'teal',
    title: 'Profilo guidato',
    description: 'Rispondi a 3 domande su orizzonte, rischio e obiettivi e ricevi un suggerimento su misura.',
  },
  {
    method: 'manual',
    icon: IconAdjustments,
    color: 'grape',
    title: 'Allocazione manuale',
    description: 'Parti da zero e componi liberamente le percentuali per ogni asset class.',
  },
];

export function CreatorMethodPicker({ onPick }: CreatorMethodPickerProps) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
      {METHODS.map(({ method, icon: Icon, color, title, description }) => (
        <Card
          key={method}
          withBorder
          radius="xl"
          padding="xl"
          style={{ cursor: 'pointer', transition: 'box-shadow 150ms ease' }}
          onClick={() => onPick(method)}
        >
          <Stack gap="md" align="center" ta="center">
            <ThemeIcon size={56} radius="xl" variant="light" color={color}>
              <Icon size={28} />
            </ThemeIcon>
            <Text fw={700} size="lg">{title}</Text>
            <Text size="sm" c="dimmed">{description}</Text>
          </Stack>
        </Card>
      ))}
    </SimpleGrid>
  );
}
