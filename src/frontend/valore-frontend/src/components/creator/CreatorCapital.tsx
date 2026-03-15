import {
  NumberInput,
  Stack,
  Text,
  Title,
  Card,
  Group,
  Box,
} from '@mantine/core';
import { AllocationDonutChart } from './AllocationDonutChart';
import type { AllocationSlot } from './types';

interface CreatorCapitalProps {
  capital: number | '';
  onChange: (value: number | '') => void;
  slots: AllocationSlot[];
}

export function CreatorCapital({ capital, onChange, slots }: CreatorCapitalProps) {
  const numericCapital = typeof capital === 'number' ? capital : 0;

  return (
    <Stack gap="lg">
      <Title order={4}>Capitale iniziale</Title>
      <Text size="sm" c="dimmed">
        Inserisci l'importo che vuoi investire. Calcoleremo automaticamente le quantità
        di ogni titolo in base ai pesi del modello.
      </Text>

      <NumberInput
        label="Importo da investire"
        placeholder="es. 10000"
        value={capital}
        onChange={(v) => onChange(typeof v === 'number' ? v : '')}
        min={1}
        step={100}
        size="lg"
        suffix=" €"
        thousandSeparator="."
        decimalSeparator=","
        hideControls={false}
      />

      {numericCapital > 0 && (
        <Card withBorder radius="xl" padding="lg">
          <Group gap="xl" align="flex-start" wrap="wrap">
            <AllocationDonutChart slots={slots} size={140} />
            <Stack gap={6} style={{ flex: 1, minWidth: 200 }}>
              {slots.map((slot) => {
                const amount = (numericCapital * slot.weight) / 100;
                return (
                  <Group key={slot.label} justify="space-between">
                    <Group gap={6}>
                      <Box
                        style={{
                          width: 10,
                          height: 10,
                          borderRadius: '50%',
                          background: slot.color,
                        }}
                      />
                      <Text size="sm">{slot.label}</Text>
                    </Group>
                    <Text size="sm" fw={600}>
                      {amount.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })}
                    </Text>
                  </Group>
                );
              })}
            </Stack>
          </Group>
        </Card>
      )}
    </Stack>
  );
}
