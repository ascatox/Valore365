import { Alert, Button, Card, Group, Stack, Text, Textarea } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconClipboardText, IconSearch, IconTrash } from '@tabler/icons-react';
import { InstantAnalyzerExamples } from './InstantAnalyzerExamples';

interface InstantAnalyzerFormProps {
  value: string;
  error: string | null;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
}

export function InstantAnalyzerForm({
  value,
  error,
  loading,
  onChange,
  onSubmit,
  onReset,
}: InstantAnalyzerFormProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <Card
      radius="xl"
      padding="xl"
      withBorder
      style={{
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #f4fbff 0%, #f5fffb 100%)',
        borderColor: isDark ? theme.colors.dark[4] : 'rgba(37, 99, 235, 0.12)',
        boxShadow: isDark ? '0 18px 40px rgba(0, 0, 0, 0.28)' : '0 18px 40px rgba(37, 99, 235, 0.08)',
      }}
    >
      <Stack gap="lg">
        <div>
          <Text tt="uppercase" fw={800} size="xs" c={isDark ? theme.colors.teal[3] : '#0f766e'}>
            Incolla le tue posizioni
          </Text>
          <Text size="sm" c={isDark ? theme.colors.gray[4] : '#334155'} mt={6}>
            Una riga per posizione. Formato: <code>TICKER QUANTITÀ</code>. Sono supportati ticker e ISIN. Esempio: <code>VWCE 10000</code>
          </Text>
          <Text size="sm" c={isDark ? theme.colors.gray[5] : '#475569'} mt={6}>
            Se alcune righe non possono essere risolte, l'analizzatore elaborera comunque quelle valide e segnalerà le altre qui sotto.
          </Text>
        </div>

        <InstantAnalyzerExamples onSelectExample={onChange} />

        <Textarea
          autosize
          minRows={10}
          maxRows={16}
          radius="lg"
          size="md"
          placeholder={'VWCE 10000\nAGGH 5000\nEIMI 2000'}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          styles={{
            input: {
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace',
              backgroundColor: isDark ? theme.colors.dark[5] : '#f8fafc',
              color: isDark ? theme.white : '#0f172a',
              borderColor: isDark ? theme.colors.dark[4] : 'rgba(37, 99, 235, 0.14)',
            },
          }}
        />

        {error && <Alert color="red" variant="light">{error}</Alert>}

        <Group justify="space-between" wrap="wrap">
          <Group gap="xs">
            <Button variant="default" leftSection={<IconClipboardText size={16} />} onClick={() => onChange(value.trim())}>
              Pulisci spazi
            </Button>
            <Button variant="subtle" color="gray" leftSection={<IconTrash size={16} />} onClick={onReset}>
              Azzera
            </Button>
          </Group>
          <Button
            size="md"
            radius="xl"
            loading={loading}
            leftSection={<IconSearch size={16} />}
            onClick={onSubmit}
          >
            Analizza Portafoglio
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
