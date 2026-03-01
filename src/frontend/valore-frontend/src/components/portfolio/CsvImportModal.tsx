import { useState } from 'react';
import {
  Badge,
  Button,
  Group,
  Modal,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconFileImport, IconCheck, IconX } from '@tabler/icons-react';
import {
  uploadCsvImportPreview,
  commitCsvImport,
  cancelCsvImport,
  type CsvImportPreviewResponse,
  type CsvImportCommitResponse,
} from '../../services/api';

interface CsvImportModalProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number;
  onImportComplete?: () => void;
}

export function CsvImportModal({ opened, onClose, portfolioId, onImportComplete }: CsvImportModalProps) {
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload');
  const [preview, setPreview] = useState<CsvImportPreviewResponse | null>(null);
  const [result, setResult] = useState<CsvImportCommitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const data = await uploadCsvImportPreview(portfolioId, file);
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
      title="Importa Transazioni da CSV"
      size="xl"
    >
      <Stack>
        {step === 'upload' && (
          <>
            <Text size="sm" c="dimmed">
              Formato CSV atteso: Operazione, Data valuta, Descrizione, Titolo, Isin, Segno, Quantita, Divisa, Prezzo, Cambio, Controvalore, Commissioni Fondi Sw/Ingr/Uscita, Commissioni Fondi Banca Corrispondente, Spese Fondi Sgr, Commissioni amministrato
            </Text>
            <Text size="xs" c="dimmed">
              Segno: A = acquisto, V = vendita. Numeri in formato italiano (1.234,56).
            </Text>
            <input
              type="file"
              accept=".csv"
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
                      <Table.Td style={{ textAlign: 'right' }}>{row.quantity?.toFixed(4) ?? '-'}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>{row.price?.toFixed(4) ?? '-'}</Table.Td>
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
            <Button onClick={handleClose}>Chiudi</Button>
          </>
        )}
      </Stack>
    </Modal>
  );
}
