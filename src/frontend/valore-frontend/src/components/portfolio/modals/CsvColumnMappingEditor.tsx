import { Alert, Button, Card, Group, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import type { CsvColumnMapping, CsvDateFormat, CsvImportMappingInfo } from '../../../services/api';

type MappingField = Exclude<keyof CsvColumnMapping, 'date_format'>;

const MAPPING_FIELDS: { key: MappingField; label: string; required: boolean }[] = [
  { key: 'trade_at', label: 'Data operazione', required: true },
  { key: 'isin', label: 'ISIN', required: true },
  { key: 'side', label: 'Acquisto / vendita', required: true },
  { key: 'quantity', label: 'Quantità', required: true },
  { key: 'price', label: 'Prezzo', required: true },
  { key: 'trade_currency', label: 'Valuta', required: false },
  { key: 'fees', label: 'Commissioni', required: false },
  { key: 'name', label: 'Titolo', required: false },
];

const DATE_FORMAT_OPTIONS: { value: CsvDateFormat; label: string }[] = [
  { value: 'DD/MM/YYYY', label: 'gg/mm/aaaa' },
  { value: 'MM/DD/YYYY', label: 'mm/gg/aaaa' },
  { value: 'YYYY-MM-DD', label: 'aaaa-mm-gg' },
  { value: 'DD-MM-YYYY', label: 'gg-mm-aaaa' },
  { value: 'DD.MM.YYYY', label: 'gg.mm.aaaa' },
  { value: 'YYYY/MM/DD', label: 'aaaa/mm/gg' },
];

interface CsvColumnMappingEditorProps {
  info: CsvImportMappingInfo;
  draft: CsvColumnMapping;
  dirty: boolean;
  applying: boolean;
  error: string | null;
  onChange: (mapping: CsvColumnMapping) => void;
  onApply: () => void;
}

export function CsvColumnMappingEditor({
  info,
  draft,
  dirty,
  applying,
  error,
  onChange,
  onApply,
}: CsvColumnMappingEditorProps) {
  return (
    <Stack gap="sm">
      <Alert
        color="yellow"
        variant="light"
        icon={<IconSparkles size={16} />}
        title={info.source === 'ai' ? 'Formato non riconosciuto' : 'Associazione delle colonne modificata'}
      >
        {info.source === 'ai'
          ? 'Le colonne del file sono state associate ai campi della transazione con l’aiuto dell’AI, che può sbagliare. '
          : 'Hai scelto tu a quale campo corrisponde ogni colonna del file. '}
        Controlla l’associazione e i dati dell’anteprima: puoi correggerla prima di importare. Nessuna transazione viene
        salvata finché non confermi l’importazione.
      </Alert>

      <Card withBorder radius="lg" padding="md">
        <Stack gap="sm">
          <Text fw={600}>Colonne del file</Text>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm">
            {MAPPING_FIELDS.map(({ key, label, required }) => (
              <Select
                key={key}
                label={required ? label : `${label} (opzionale)`}
                data={info.columns}
                value={draft[key]}
                onChange={(value) => {
                  if (value !== null || !required) onChange({ ...draft, [key]: value });
                }}
                allowDeselect={!required}
                clearable={!required}
                searchable
                nothingFoundMessage="Nessuna colonna"
              />
            ))}
            <Select
              label="Formato data"
              data={DATE_FORMAT_OPTIONS}
              value={draft.date_format}
              onChange={(value) => {
                if (value) onChange({ ...draft, date_format: value as CsvDateFormat });
              }}
              allowDeselect={false}
            />
          </SimpleGrid>

          {error && <Text c="red" size="sm">{error}</Text>}

          <Group justify="flex-end" align="center">
            {dirty && (
              <Text size="sm" c="dimmed">
                Applica la nuova associazione per aggiornare l’anteprima.
              </Text>
            )}
            <Button variant="light" onClick={onApply} loading={applying} disabled={!dirty}>
              Applica associazione
            </Button>
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}
