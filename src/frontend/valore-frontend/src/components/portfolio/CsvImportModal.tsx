import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Avatar,
  Badge,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconFileImport, IconCheck, IconX, IconChartPie } from '@tabler/icons-react';
import { formatNum } from '../dashboard/formatters';
import {
  uploadCsvImportPreview,
  commitCsvImport,
  cancelCsvImport,
  type CsvImportPreviewResponse,
  type CsvImportCommitResponse,
} from '../../services/api';

const BROKER_OPTIONS = [
  { value: 'fineco', label: 'Fineco', logo: '/logos/fineco.svg' },
];

interface CsvImportModalProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number;
  onImportComplete?: () => void;
}

function BrokerSelectOption({ logo, label }: { logo: string; label: string }) {
  return (
    <Group gap="sm" wrap="nowrap">
      <Avatar src={logo} size={24} radius="sm" />
      <Text size="sm">{label}</Text>
    </Group>
  );
}

export function CsvImportModal({ opened, onClose, portfolioId, onImportComplete }: CsvImportModalProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload');
  const [broker, setBroker] = useState<string>('fineco');
  const [preview, setPreview] = useState<CsvImportPreviewResponse | null>(null);
  const [result, setResult] = useState<CsvImportCommitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedBroker = BROKER_OPTIONS.find((b) => b.value === broker);

  const handleClose = () => {
    if (preview && step === 'preview') {
      cancelCsvImport(preview.batch_id).catch(() => {});
    }
    setStep('upload');
    setPreview(null);
    setResult(null);
    setError(null);
    onClose();
  };

  const handleFileUpload = async (file: File) => {
    try {
      setLoading(true);
      setError(null);
      const data = await uploadCsvImportPreview(portfolioId, file, broker);
      setPreview(data);
      setStep('preview');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!preview) return;
    try {
      setLoading(true);
      setError(null);
      const commitResult = await commitCsvImport(preview.batch_id);
      setResult(commitResult);
      setStep('done');
      onImportComplete?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="Importa Operazioni"
      size="xl"
    >
      <Stack>
        {step === 'upload' && (
          <>
            <Select
              label="Broker"
              placeholder="Seleziona il broker"
              data={BROKER_OPTIONS.map((b) => ({ value: b.value, label: b.label }))}
              value={broker}
              onChange={(v) => v && setBroker(v)}
              allowDeselect={false}
              renderOption={({ option }) => {
                const b = BROKER_OPTIONS.find((x) => x.value === option.value);
                return b ? <BrokerSelectOption logo={b.logo} label={b.label} /> : <Text size="sm">{option.label}</Text>;
              }}
              leftSection={selectedBroker ? <Avatar src={selectedBroker.logo} size={20} radius="sm" /> : undefined}
            />

            <Text size="sm" c="dimmed">
              Seleziona il file esportato dal tuo broker. Sono supportati i formati CSV e Excel (XLSX).
            </Text>

            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
              style={{ marginTop: 8 }}
            />
            {loading && <Text size="sm">Analisi in corso...</Text>}
            {error && <Text c="red" size="sm">{error}</Text>}
          </>
        )}

        {step === 'preview' && preview && (
          <>
            <Group>
              {selectedBroker && (
                <Badge
                  size="lg"
                  variant="light"
                  leftSection={<Avatar src={selectedBroker.logo} size={16} radius="sm" />}
                >
                  {selectedBroker.label}
                </Badge>
              )}
              <Badge color="blue" size="lg">Totale: {preview.total_rows}</Badge>
              <Badge color="green" size="lg">Valide: {preview.valid_rows}</Badge>
              {preview.error_rows > 0 && (
                <Badge color="red" size="lg">Errori: {preview.error_rows}</Badge>
              )}
            </Group>

            <Table.ScrollContainer minWidth={600}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>#</Table.Th>
                    <Table.Th>Stato</Table.Th>
                    <Table.Th>Data</Table.Th>
                    <Table.Th>ISIN</Table.Th>
                    <Table.Th>Titolo</Table.Th>
                    <Table.Th>Operazione</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Qta</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Prezzo</Table.Th>
                    <Table.Th>Errori</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {preview.rows.map((row) => (
                    <Table.Tr key={row.row_number} bg={row.valid ? undefined : 'red.0'}>
                      <Table.Td>{row.row_number}</Table.Td>
                      <Table.Td>
                        {row.valid
                          ? <IconCheck size={16} color="green" />
                          : <IconX size={16} color="red" />
                        }
                      </Table.Td>
                      <Table.Td>{row.trade_at ? new Date(row.trade_at).toLocaleDateString('it-IT') : '-'}</Table.Td>
                      <Table.Td>{row.isin || '-'}</Table.Td>
                      <Table.Td>{row.titolo || row.asset_name || '-'}</Table.Td>
                      <Table.Td>{row.side || '-'}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>{row.quantity != null ? formatNum(row.quantity, 4) : '-'}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>{row.price != null ? formatNum(row.price, 4) : '-'}</Table.Td>
                      <Table.Td>
                        {row.errors.length > 0 && (
                          <Text size="xs" c="red">{row.errors.join('; ')}</Text>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            {error && <Text c="red" size="sm">{error}</Text>}

            <Group justify="flex-end">
              <Button variant="outline" onClick={handleClose}>Annulla</Button>
              <Button
                onClick={handleCommit}
                loading={loading}
                disabled={preview.valid_rows === 0}
                leftSection={<IconFileImport size={16} />}
              >
                Importa {preview.valid_rows} transazioni
              </Button>
            </Group>
          </>
        )}

        {step === 'done' && result && (
          <>
            <Text size="lg" fw={600} c="green">Importazione completata</Text>
            <Text>Transazioni create: {result.committed_transactions}</Text>
            {result.errors.length > 0 && (
              <Stack gap="xs">
                <Text fw={500} c="red">Errori:</Text>
                {result.errors.map((e, i) => (
                  <Text key={i} size="sm" c="red">{e}</Text>
                ))}
              </Stack>
            )}
            <Text size="sm" c="dimmed">
              Vai alla Dashboard per visualizzare le posizioni e il P/L del portafoglio.
            </Text>
            <Group justify="flex-end">
              <Button variant="outline" onClick={handleClose}>Chiudi</Button>
              <Button
                leftSection={<IconChartPie size={16} />}
                onClick={() => {
                  handleClose();
                  navigate('/');
                  window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
                }}
              >
                Vai alla Dashboard
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  );
}
