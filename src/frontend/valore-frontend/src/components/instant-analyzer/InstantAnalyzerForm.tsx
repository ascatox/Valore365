import {
  Alert,
  Box,
  Button,
  FileButton,
  Group,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconFileImport, IconPlayerPlay, IconPlus, IconTrash, IconUpload, IconX } from '@tabler/icons-react';
import { InstantAnalyzerExamples } from './InstantAnalyzerExamples';

export interface ManualPositionDraft {
  id: string;
  identifier: string;
  value: string;
}

interface InstantAnalyzerFormProps {
  mode: 'demo' | 'manual' | 'csv';
  value: string;
  error: string | null;
  loading: boolean;
  csvImporting: boolean;
  csvSummary: string | null;
  csvFileName: string | null;
  onModeChange: (value: 'demo' | 'manual' | 'csv') => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
  onSelectExample: (value: string) => void;
  manualPositions: ManualPositionDraft[];
  onManualChange: (id: string, field: 'identifier' | 'value', value: string) => void;
  onManualAdd: () => void;
  onManualRemove: (id: string) => void;
  onCsvFileSelect: (file: File | null) => void;
}

export function InstantAnalyzerForm({
  mode,
  value,
  error,
  loading,
  csvImporting,
  csvSummary,
  csvFileName,
  onModeChange,
  onChange,
  onSubmit,
  onReset,
  onSelectExample,
  manualPositions,
  onManualChange,
  onManualAdd,
  onManualRemove,
  onCsvFileSelect,
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
        background: isDark ? theme.colors.dark[6] : '#ffffff',
        padding: 24,
        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <Stack gap="lg">
        <div>
          <Text fw={700} c={isDark ? 'white' : '#111827'} mb={4}>
            Importa il portafoglio
          </Text>
          <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
            Scegli la modalita piu veloce per arrivare ai 3 insight principali.
          </Text>
        </div>

        <SegmentedControl
          fullWidth
          radius="md"
          value={mode}
          onChange={(next) => onModeChange(next as 'demo' | 'manual' | 'csv')}
          data={[
            { label: 'Demo mode', value: 'demo' },
            { label: 'Manuale', value: 'manual' },
            { label: 'CSV Fineco', value: 'csv' },
          ]}
        />

        {mode === 'demo' && (
          <Stack gap="md">
            <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
              Una riga per posizione. Formato: <code style={{ background: isDark ? theme.colors.dark[4] : '#f3f4f6', padding: '2px 6px', borderRadius: 4, fontSize: '0.85em' }}>TICKER VALORE</code>
            </Text>
            <InstantAnalyzerExamples onSelectExample={(example) => {
              onSelectExample(example);
              onChange(example);
            }} />
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
          </Stack>
        )}

        {mode === 'manual' && (
          <Stack gap="sm">
            <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
              Inserisci solo identificativo e valore totale di ogni posizione.
            </Text>
            {manualPositions.map((position, index) => (
              <Group key={position.id} align="flex-end" grow wrap="nowrap">
                <TextInput
                  label={index === 0 ? 'Ticker o ISIN' : undefined}
                  placeholder="VWCE"
                  value={position.identifier}
                  onChange={(event) => onManualChange(position.id, 'identifier', event.currentTarget.value)}
                />
                <TextInput
                  label={index === 0 ? 'Valore' : undefined}
                  placeholder="10000"
                  value={position.value}
                  onChange={(event) => onManualChange(position.id, 'value', event.currentTarget.value)}
                />
                <Button
                  variant="subtle"
                  color="gray"
                  onClick={() => onManualRemove(position.id)}
                  disabled={manualPositions.length === 1}
                >
                  <IconX size={16} />
                </Button>
              </Group>
            ))}
            <Group justify="space-between">
              <Button variant="light" leftSection={<IconPlus size={16} />} onClick={onManualAdd}>
                Aggiungi riga
              </Button>
              <Text size="xs" c="dimmed">
                Minimo indispensabile: identificativo + valore.
              </Text>
            </Group>
          </Stack>
        )}

        {mode === 'csv' && (
          <Stack gap="md">
            <Alert color="teal" variant="light" radius="md" icon={<IconFileImport size={16} />}>
              Carica un export Fineco CSV o Excel. Ricostruiamo un portafoglio indicativo aggregando acquisti e vendite per ISIN.
            </Alert>

            <Group justify="space-between" align="center">
              <FileButton onChange={onCsvFileSelect} accept=".csv,.xlsx,.xls">
                {(props) => (
                  <Button
                    {...props}
                    variant="light"
                    leftSection={<IconUpload size={16} />}
                    loading={csvImporting}
                  >
                    Carica file Fineco
                  </Button>
                )}
              </FileButton>
              {csvFileName && (
                <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                  {csvFileName}
                </Text>
              )}
            </Group>

            {csvSummary && (
              <Alert color="blue" variant="light" radius="md">
                {csvSummary}
              </Alert>
            )}

            <Textarea
              autosize
              minRows={8}
              maxRows={14}
              radius="md"
              size="md"
              readOnly
              placeholder="Dopo il parsing del file vedrai qui le posizioni estratte."
              value={value}
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
          </Stack>
        )}

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
