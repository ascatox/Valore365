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
}

export function CreatorConfirm({
  slots,
  portfolioName,
  onNameChange,
  onConfirm,
  loading,
}: CreatorConfirmProps) {
  const total = slots.reduce((s, sl) => s + sl.weight, 0);
  const canConfirm = portfolioName.trim().length > 0 && Math.abs(total - 100) < 0.5;

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
            {slots.map((slot) => (
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
                <Text size="sm" fw={600}>{slot.weight} %</Text>
              </Group>
            ))}
          </Stack>
        </Group>
      </Card>

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
