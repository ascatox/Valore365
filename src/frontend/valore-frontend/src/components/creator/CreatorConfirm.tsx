import {
  Box,
  Button,
  Card,
  Group,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconRocket } from '@tabler/icons-react';
import { AllocationDonutChart } from './AllocationDonutChart';
import type { AllocationSlot } from './types';

interface CreatorConfirmProps {
  slots: AllocationSlot[];
  portfolioName: string;
  onNameChange: (name: string) => void;
  onConfirm: () => void;
  loading: boolean;
  capital: number;
}

export function CreatorConfirm({
  slots,
  portfolioName,
  onNameChange,
  onConfirm,
  loading,
  capital,
}: CreatorConfirmProps) {
  const total = slots.reduce((s, sl) => s + sl.weight, 0);
  const canConfirm = portfolioName.trim().length > 0 && Math.abs(total - 100) < 0.5 && capital > 0;

  const fmtEur = (v: number) =>
    v.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });

  return (
    <Stack gap="lg">
      <Title order={4}>Conferma e crea</Title>

      <TextInput
        label="Nome del portafoglio"
        placeholder="es. Il mio All Weather"
        value={portfolioName}
        onChange={(e) => onNameChange(e.currentTarget.value)}
        size="md"
      />

      <Card withBorder radius="xl" padding="lg">
        <Group gap="xl" align="flex-start" wrap="wrap">
          <AllocationDonutChart slots={slots} size={160} />
          <Stack gap={6} style={{ flex: 1, minWidth: 200 }}>
            {slots.map((slot) => {
              const amount = (capital * slot.weight) / 100;
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
                  <Group gap="xs">
                    <Text size="sm" c="dimmed">{slot.weight} %</Text>
                    <Text size="sm" fw={600}>{fmtEur(amount)}</Text>
                  </Group>
                </Group>
              );
            })}
            <Group justify="space-between" mt="xs" pt="xs" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
              <Text size="sm" fw={700}>Totale investito</Text>
              <Text size="sm" fw={700}>{fmtEur(capital)}</Text>
            </Group>
          </Stack>
        </Group>
      </Card>

      <Text size="xs" c="dimmed">
        Verranno create transazioni di acquisto ai prezzi correnti di mercato per ogni titolo,
        proporzionalmente ai pesi del modello.
      </Text>

      <Button
        size="lg"
        fullWidth
        leftSection={<IconRocket size={20} />}
        disabled={!canConfirm}
        loading={loading}
        onClick={onConfirm}
      >
        Crea portafoglio
      </Button>
    </Stack>
  );
}
