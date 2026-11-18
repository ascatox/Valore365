import { Button, Group, Stack, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';

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
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  // Brand colour of the active colour theme: shade 6 in light, 4 in dark (as petrol).
  const brand = isDark ? theme.colors.teal[4] : theme.colors.teal[6];
  const brandBorder = theme.colors.teal[2];

  return (
    <Stack gap="xs">
      <Text fw={600} size="xs" tt="uppercase" c={isDark ? theme.colors.gray[5] : '#9ca3af'} style={{ letterSpacing: '0.05em' }}>
        Prova un esempio
      </Text>
      <Group gap="xs">
        {EXAMPLES.map((example) => (
          <Button
            key={example.label}
            variant="default"
            size="xs"
            radius="md"
            onClick={() => onSelectExample(example.value)}
            style={{
              borderColor: isDark ? theme.colors.dark[4] : brandBorder,
              color: brand,
              fontWeight: 600,
              transition: 'all 300ms ease',
            }}
          >
            {example.label}
          </Button>
        ))}
      </Group>
    </Stack>
  );
}
