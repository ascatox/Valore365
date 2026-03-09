import { Alert, Button, Card, Group, Stack, Text, Textarea } from '@mantine/core';
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
  return (
    <Card
      radius="xl"
      padding="xl"
      withBorder
      style={{
        background: 'linear-gradient(180deg, #fffaf0 0%, #fffdf8 100%)',
        borderColor: 'rgba(15, 23, 42, 0.1)',
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)',
      }}
    >
      <Stack gap="lg">
        <div>
          <Text tt="uppercase" fw={800} size="xs" c="#7c2d12">Incolla le tue posizioni</Text>
          <Text size="sm" c="#334155" mt={6}>
            Una riga per posizione. Formato: <code>IDENTIFICATIVO VALORE</code>. Sono supportati ticker e ISIN. Esempio: <code>VWCE 10000</code>
          </Text>
          <Text size="sm" c="#475569" mt={6}>
            Se alcune righe non possono essere risolte, l’analizzatore elaborera comunque quelle valide e segnalerà le altre qui sotto.
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
              backgroundColor: '#f8fafc',
              color: '#0f172a',
              borderColor: 'rgba(15, 23, 42, 0.12)',
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
