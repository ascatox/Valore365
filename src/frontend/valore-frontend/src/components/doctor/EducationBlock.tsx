import { Badge, Button, Card, Group, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconBook2, IconMessageCircleBolt } from '@tabler/icons-react';
import type { PortfolioHealthEducation } from '../../services/api';

interface EducationBlockProps {
  education: PortfolioHealthEducation;
  onPromptSelect?: (prompt: string) => void;
}

export function EducationBlock({ education, onPromptSelect }: EducationBlockProps) {
  return (
    <Card withBorder radius="lg" padding="lg" bg="var(--mantine-color-gray-0)">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <Group gap="sm" align="flex-start">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconBook2 size={18} />
            </ThemeIcon>
            <div>
              <Text size="xs" tt="uppercase" fw={800} c="dimmed">
                Educazione finanziaria
              </Text>
              <Text fw={700} mt={4}>{education.title}</Text>
            </div>
          </Group>
          <Badge variant="light" color="teal" radius="xl">
            {education.concept}
          </Badge>
        </Group>

        <EducationRow label="Cosa significa" value={education.what_it_means} />
        <EducationRow label="Perche' conta" value={education.why_it_matters} />
        <EducationRow label="Come leggerlo nel tuo portafoglio" value={education.how_to_read_it} />

        {onPromptSelect && education.copilot_prompts.length > 0 && (
          <Stack gap="xs">
            <Text size="xs" tt="uppercase" fw={800} c="dimmed">
              Approfondisci col Copilot
            </Text>
            <Group gap="xs">
              {education.copilot_prompts.map((prompt) => (
                <Button
                  key={prompt}
                  variant="light"
                  color="teal"
                  radius="xl"
                  size="xs"
                  leftSection={<IconMessageCircleBolt size={14} />}
                  onClick={() => onPromptSelect(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </Group>
          </Stack>
        )}
      </Stack>
    </Card>
  );
}

function EducationRow({ label, value }: { label: string; value: string }) {
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
