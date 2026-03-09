import { Button, Group, Stack, Text } from '@mantine/core';

interface InstantAnalyzerExamplesProps {
  onSelectExample: (value: string) => void;
}

const EXAMPLES = [
  {
    label: 'ETF Globale',
    value: 'VWCE 10000\nAGGH 5000\nEIMI 2000',
  },
  {
    label: 'Mondo + S&P 500',
    value: 'SWDA 12000\nCSPX 6000\nAGGH 4000',
  },
  {
    label: 'Tech Concentrato',
    value: 'AAPL 9000\nMSFT 7000\nVWCE 3000',
  },
];

export function InstantAnalyzerExamples({ onSelectExample }: InstantAnalyzerExamplesProps) {
  return (
    <Stack gap="xs">
      <Text fw={700} size="sm" c="#334155">
        Prova un esempio
      </Text>
      <Group gap="xs">
        {EXAMPLES.map((example) => (
          <Button key={example.label} variant="light" radius="xl" onClick={() => onSelectExample(example.value)}>
            {example.label}
          </Button>
        ))}
      </Group>
    </Stack>
  );
}
