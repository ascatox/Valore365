import { useEffect, useMemo, useState } from 'react';
import { Badge, Box, Button, Card, Group, Radio, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconCheck, IconSparkles } from '@tabler/icons-react';
import { AllocationDonutChart } from './AllocationDonutChart';
import { RISK_META, recommendPortfolioModels } from './models';
import type { PortfolioModel, ProfileAnswers } from './types';

interface CreatorProfileQuizProps {
  selectedModelId: string | null;
  onSelectModel: (model: PortfolioModel) => void;
  onAnswersChange?: (answers: ProfileAnswers | null) => void;
}

const HORIZON_OPTIONS: Array<{ value: ProfileAnswers['horizon']; label: string }> = [
  { value: 'lt5', label: 'Meno di 5 anni' },
  { value: '5to10', label: '5-10 anni' },
  { value: '10to20', label: '10-20 anni' },
  { value: 'gt20', label: 'Oltre 20 anni' },
];

const RISK_OPTIONS: Array<{ value: ProfileAnswers['riskTolerance']; label: string }> = [
  { value: 'sell_all', label: 'Venderei tutto subito' },
  { value: 'sell_some', label: 'Venderei una parte per proteggermi' },
  { value: 'hold', label: 'Non farei nulla, aspetterei' },
  { value: 'buy_more', label: 'Comprerei di piu\' a sconto' },
];

const OBJECTIVE_OPTIONS: Array<{ value: ProfileAnswers['objective']; label: string }> = [
  { value: 'capital_preservation', label: 'Proteggere il capitale' },
  { value: 'moderate_growth', label: 'Crescita moderata con poca volatilita\'' },
  { value: 'max_growth', label: 'Massimizzare la crescita nel lungo periodo' },
  { value: 'income', label: 'Generare rendita periodica' },
];

interface QuizQuestionProps<T extends string> {
  title: string;
  description?: string;
  value: T | null;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}

function QuizQuestion<T extends string>({
  title,
  description,
  value,
  options,
  onChange,
}: QuizQuestionProps<T>) {
  return (
    <Card withBorder radius="xl" padding="lg">
      <Stack gap="sm">
        <div>
          <Text fw={700}>{title}</Text>
          {description && (
            <Text size="sm" c="dimmed" mt={4}>
              {description}
            </Text>
          )}
        </div>
        <Radio.Group value={value} onChange={(nextValue) => onChange(nextValue as T)}>
          <Stack gap="xs">
            {options.map((option) => (
              <Radio.Card key={option.value} value={option.value} radius="lg" p="md">
                <Text size="sm">{option.label}</Text>
              </Radio.Card>
            ))}
          </Stack>
        </Radio.Group>
      </Stack>
    </Card>
  );
}

export function CreatorProfileQuiz({
  selectedModelId,
  onSelectModel,
  onAnswersChange,
}: CreatorProfileQuizProps) {
  const [answers, setAnswers] = useState<ProfileAnswers>({
    horizon: '10to20',
    riskTolerance: 'hold',
    objective: 'moderate_growth',
  });

  useEffect(() => {
    onAnswersChange?.(answers);
  }, [answers, onAnswersChange]);

  const recommendations = useMemo(
    () => recommendPortfolioModels(answers, 2),
    [answers],
  );

  return (
    <Stack gap="lg">
      <div>
        <Title order={4}>Profilo guidato</Title>
        <Text size="sm" c="dimmed" mt={4}>
          Rispondi a 3 domande e scegli il modello piu' coerente con il tuo profilo.
        </Text>
      </div>

      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
        <QuizQuestion
          title="1. Orizzonte temporale"
          value={answers.horizon}
          options={HORIZON_OPTIONS}
          onChange={(horizon) => setAnswers((current) => ({ ...current, horizon }))}
        />
        <QuizQuestion
          title="2. Tolleranza al rischio"
          description="Se il portafoglio perdesse il 30% in un mese, cosa faresti?"
          value={answers.riskTolerance}
          options={RISK_OPTIONS}
          onChange={(riskTolerance) => setAnswers((current) => ({ ...current, riskTolerance }))}
        />
        <QuizQuestion
          title="3. Obiettivo principale"
          value={answers.objective}
          options={OBJECTIVE_OPTIONS}
          onChange={(objective) => setAnswers((current) => ({ ...current, objective }))}
        />
      </SimpleGrid>

      <Card withBorder radius="xl" padding="lg">
        <Stack gap="lg">
          <Group justify="space-between" wrap="wrap" gap="xs">
            <div>
              <Text fw={700}>Modelli consigliati</Text>
              <Text size="sm" c="dimmed">
                Ti proponiamo le 2 opzioni piu' vicine alle risposte date.
              </Text>
            </div>
            <Badge leftSection={<IconSparkles size={12} />} variant="light" color="teal">
              Suggerimento automatico
            </Badge>
          </Group>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            {recommendations.map(({ model, reason }) => {
              const isSelected = selectedModelId === model.id;
              const risk = RISK_META[model.risk];

              return (
                <Card
                  key={model.id}
                  withBorder
                  radius="xl"
                  padding="lg"
                  style={{
                    outline: isSelected ? '2px solid var(--mantine-color-teal-6)' : undefined,
                  }}
                >
                  <Stack gap="sm">
                    <Group justify="space-between" align="flex-start">
                      <div>
                        <Text fw={700}>{model.name}</Text>
                        <Text size="xs" c="dimmed">{model.subtitle}</Text>
                      </div>
                      {isSelected && (
                        <Badge color="teal" variant="filled" circle size="lg">
                          <IconCheck size={14} />
                        </Badge>
                      )}
                    </Group>

                    <Badge color={risk.color} variant="light" w="fit-content">
                      Rischio {risk.label.toLowerCase()}
                    </Badge>

                    <Box h={150}>
                      <AllocationDonutChart slots={model.slots} size={150} />
                    </Box>

                    <Text size="sm">{reason}</Text>

                    <Button
                      variant={isSelected ? 'filled' : 'light'}
                      color="teal"
                      onClick={() => onSelectModel(model)}
                    >
                      {isSelected ? 'Selezionato' : 'Scegli questo modello'}
                    </Button>
                  </Stack>
                </Card>
              );
            })}
          </SimpleGrid>
        </Stack>
      </Card>
    </Stack>
  );
}
