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
    <Card radius="xl" padding="xl" withBorder style={{ background: 'linear-gradient(180deg, #fffdf8 0%, #ffffff 100%)' }}>
      <Stack gap="lg">
        <div>
          <Text tt="uppercase" fw={800} size="xs" c="dimmed">Paste your holdings</Text>
          <Text size="sm" c="dimmed" mt={6}>
            One line per position. Format: <code>IDENTIFIER VALUE</code>. Example: <code>VWCE 10000</code>
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
            },
          }}
        />

        {error && <Alert color="red" variant="light">{error}</Alert>}

        <Group justify="space-between" wrap="wrap">
          <Group gap="xs">
            <Button variant="default" leftSection={<IconClipboardText size={16} />} onClick={() => onChange(value.trim())}>
              Clean spacing
            </Button>
            <Button variant="subtle" color="gray" leftSection={<IconTrash size={16} />} onClick={onReset}>
              Reset
            </Button>
          </Group>
          <Button
            size="md"
            radius="xl"
            loading={loading}
            leftSection={<IconSearch size={16} />}
            onClick={onSubmit}
          >
            Analyze Portfolio
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
