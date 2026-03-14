import { useState } from 'react';
import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
  SegmentedControl,
} from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import { PORTFOLIO_MODELS, RISK_META } from './models';
import { AllocationDonutChart } from './AllocationDonutChart';
import type { PortfolioModel, RiskLevel } from './types';

interface CreatorModelLibraryProps {
  selected: string | null;
  onSelect: (model: PortfolioModel) => void;
}

const RISK_FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'Tutti' },
  { value: 'low', label: 'Basso' },
  { value: 'medium', label: 'Medio' },
  { value: 'high', label: 'Alto' },
];

function matchesFilter(risk: RiskLevel, filter: string): boolean {
  if (filter === 'all') return true;
  if (filter === 'low') return risk === 'low' || risk === 'medium-low';
  if (filter === 'medium') return risk === 'medium';
  return risk === 'high' || risk === 'very-high';
}

function RiskBars({ level }: { level: RiskLevel }) {
  const meta = RISK_META[level];
  return (
    <Group gap={3}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Box
          key={i}
          style={{
            width: 4,
            height: 10 + i * 2,
            borderRadius: 2,
            background:
              i <= meta.bars
                ? `var(--mantine-color-${meta.color}-6)`
                : 'var(--mantine-color-default-border)',
          }}
        />
      ))}
    </Group>
  );
}

export function CreatorModelLibrary({ selected, onSelect }: CreatorModelLibraryProps) {
  const [filter, setFilter] = useState('all');
  const filtered = PORTFOLIO_MODELS.filter((m) => matchesFilter(m.risk, filter));

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <Title order={4}>Scegli un modello</Title>
        <SegmentedControl
          size="xs"
          data={RISK_FILTERS}
          value={filter}
          onChange={setFilter}
        />
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {filtered.map((model) => {
          const isSelected = selected === model.id;
          const meta = RISK_META[model.risk];
          return (
            <Card
              key={model.id}
              withBorder
              radius="xl"
              padding="lg"
              style={{
                cursor: 'pointer',
                outline: isSelected
                  ? '2px solid var(--mantine-color-blue-6)'
                  : undefined,
                transition: 'outline 150ms ease, box-shadow 150ms ease',
              }}
              onClick={() => onSelect(model)}
            >
              <Stack gap="sm">
                <Group justify="space-between" align="flex-start">
                  <Stack gap={2}>
                    <Text fw={700} size="lg">{model.name}</Text>
                    <Text size="xs" c="dimmed">{model.subtitle}</Text>
                  </Stack>
                  {isSelected && (
                    <Badge circle size="lg" color="blue" variant="filled">
                      <IconCheck size={14} />
                    </Badge>
                  )}
                </Group>

                <Group gap="xs">
                  <RiskBars level={model.risk} />
                  <Badge size="sm" color={meta.color} variant="light">
                    {meta.label}
                  </Badge>
                </Group>

                <AllocationDonutChart slots={model.slots} size={140} />

                <Stack gap={4}>
                  {model.slots.map((slot) => (
                    <Group key={slot.label} justify="space-between" gap="xs">
                      <Group gap={6}>
                        <Box
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            background: slot.color,
                            flexShrink: 0,
                          }}
                        />
                        <Text size="xs" c="dimmed">{slot.label}</Text>
                      </Group>
                      <Text size="xs" fw={600}>{slot.weight} %</Text>
                    </Group>
                  ))}
                </Stack>

                <Text size="xs" c="dimmed" lineClamp={2}>
                  {model.description}
                </Text>

                <Button
                  variant={isSelected ? 'filled' : 'light'}
                  size="sm"
                  fullWidth
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(model);
                  }}
                >
                  {isSelected ? 'Selezionato' : 'Seleziona'}
                </Button>
              </Stack>
            </Card>
          );
        })}
      </SimpleGrid>
    </Stack>
  );
}
