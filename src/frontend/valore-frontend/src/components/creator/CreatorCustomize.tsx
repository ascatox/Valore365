import {
  Box,
  Button,
  Group,
  SimpleGrid,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { AllocationDonutChart } from './AllocationDonutChart';
import type { AllocationSlot } from './types';

interface CreatorCustomizeProps {
  slots: AllocationSlot[];
  onChange: (slots: AllocationSlot[]) => void;
}

export function CreatorCustomize({ slots, onChange }: CreatorCustomizeProps) {
  const total = slots.reduce((s, sl) => s + sl.weight, 0);
  const isValid = Math.abs(total - 100) < 0.5;

  const updateWeight = (index: number, weight: number) => {
    const next = slots.map((sl, i) => (i === index ? { ...sl, weight } : sl));
    onChange(next);
  };

  const removeSlot = (index: number) => {
    onChange(slots.filter((_, i) => i !== index));
  };

  return (
    <Stack gap="lg">
      <Title order={4}>Personalizza l'allocazione</Title>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        <AllocationDonutChart slots={slots} size={220} />

        <Stack gap="md">
          {slots.map((slot, i) => (
            <Group key={slot.label} gap="sm" wrap="nowrap">
              <Box
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  background: slot.color,
                  flexShrink: 0,
                }}
              />
              <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                <Group justify="space-between">
                  <Text size="sm" truncate>{slot.label}</Text>
                  <Text size="sm" fw={600}>{slot.weight} %</Text>
                </Group>
                <Slider
                  min={0}
                  max={100}
                  step={0.5}
                  value={slot.weight}
                  onChange={(v) => updateWeight(i, v)}
                  color={isValid ? 'blue' : 'red'}
                  size="sm"
                  label={(v) => `${v} %`}
                />
              </Stack>
              {slots.length > 1 && (
                <Button
                  variant="subtle"
                  color="red"
                  size="compact-xs"
                  onClick={() => removeSlot(i)}
                >
                  x
                </Button>
              )}
            </Group>
          ))}

          <Group justify="space-between">
            <Text size="sm" fw={600} c={isValid ? 'teal' : 'red'}>
              Totale: {total.toFixed(1)} %
            </Text>
            {!isValid && (
              <Text size="xs" c="red">
                Il totale deve essere 100 %
              </Text>
            )}
          </Group>
        </Stack>
      </SimpleGrid>
    </Stack>
  );
}
