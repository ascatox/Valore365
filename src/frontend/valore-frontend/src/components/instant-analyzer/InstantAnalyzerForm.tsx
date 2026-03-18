import { Alert, Box, Button, Group, Stack, Text, Textarea } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconPlayerPlay, IconTrash } from '@tabler/icons-react';
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

  const emerald = '#10b981';
  const emeraldDark = '#059669';

  return (
    <Box
      style={{
        borderRadius: 16,
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
        background: isDark
          ? theme.colors.dark[6]
          : '#ffffff',
        padding: 24,
        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <Stack gap="lg">
        <div>
          <Text fw={700} c={isDark ? 'white' : '#111827'} mb={4}>
            Incolla le tue posizioni
          </Text>
          <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
            Una riga per posizione. Formato: <code style={{ background: isDark ? theme.colors.dark[4] : '#f3f4f6', padding: '2px 6px', borderRadius: 4, fontSize: '0.85em' }}>TICKER QUANTITA</code>
          </Text>
        </div>

        <InstantAnalyzerExamples onSelectExample={onChange} />

        <Textarea
          autosize
          minRows={8}
          maxRows={14}
          radius="md"
          size="md"
          placeholder={'VWCE 10000\nAGGH 5000\nEIMI 2000'}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          styles={{
            input: {
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace',
              backgroundColor: isDark ? theme.colors.dark[5] : '#f9fafb',
              color: isDark ? theme.white : '#111827',
              borderColor: isDark ? theme.colors.dark[4] : '#e5e7eb',
              fontSize: '0.9rem',
            },
          }}
        />

        {error && <Alert color="red" variant="light" radius="md">{error}</Alert>}

        <Stack gap="sm">
          <Button
            fullWidth
            size="md"
            radius="md"
            loading={loading}
            leftSection={<IconPlayerPlay size={18} />}
            onClick={onSubmit}
            style={{
              background: `linear-gradient(135deg, ${emerald} 0%, ${emeraldDark} 100%)`,
              border: 'none',
              boxShadow: `0 4px 14px rgba(16, 185, 129, 0.3)`,
              fontWeight: 700,
              transition: 'all 300ms ease',
            }}
          >
            Analizza Portafoglio
          </Button>
          <Button
            fullWidth
            variant="default"
            size="sm"
            radius="md"
            leftSection={<IconTrash size={14} />}
            onClick={onReset}
            style={{
              borderColor: isDark ? theme.colors.dark[4] : '#e5e7eb',
              color: isDark ? theme.colors.gray[4] : '#6b7280',
              fontWeight: 600,
            }}
          >
            Azzera tutto
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
