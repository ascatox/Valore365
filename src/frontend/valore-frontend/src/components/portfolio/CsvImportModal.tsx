import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Avatar,
  Badge,
  Button,
  Card,
  Group,
  List,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Alert,
} from '@mantine/core';
import { IconFileImport, IconCheck, IconX, IconChartPie } from '@tabler/icons-react';
import { formatNum } from '../dashboard/formatters';
import {
  downloadCsvImportTemplate,
  uploadCsvImportPreview,
  commitCsvImport,
  cancelCsvImport,
  createPortfolio,
  type CsvImportPreviewResponse,
  type CsvImportCommitResponse,
} from '../../services/api';

const BROKER_OPTIONS = [
  { value: 'fineco', label: 'Fineco', logo: '/logos/fineco.svg' },
  { value: 'generic', label: 'Generico' },
];

const GENERIC_REQUIRED_COLUMNS = ['operazione', 'isin', 'segno', 'quantita', 'prezzo'];
const GENERIC_OPTIONAL_COLUMNS = [
  'titolo',
  'descrizione',
  'divisa',
  'controvalore',
  'commissioni fondi sw/ingr/uscita',
  'commissioni fondi banca corrispondente',
  'spese fondi sgr',
  'commissioni amministrato',
];

interface CsvImportModalProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number | null;
  onImportComplete?: (portfolioId: number) => void;
  onPortfolioCreated?: (portfolioId: number) => void;
}

function BrokerSelectOption({ logo, label }: { logo?: string; label: string }) {
  return (
    <Group gap="sm" wrap="nowrap">
      <Avatar src={logo} size={24} radius="sm" color={logo ? undefined : 'blue'}>
        {!logo ? label.slice(0, 1) : null}
      </Avatar>
      <Text size="sm">{label}</Text>
    </Group>
  );
}

export function CsvImportModal({
  opened,
  onClose,
  portfolioId,
  onImportComplete,
  onPortfolioCreated,
}: CsvImportModalProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload');
  const [broker, setBroker] = useState<string>('fineco');
  const [preview, setPreview] = useState<CsvImportPreviewResponse | null>(null);
  const [result, setResult] = useState<CsvImportCommitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [resolvedPortfolioId, setResolvedPortfolioId] = useState<number | null>(portfolioId);
  const [portfolioName, setPortfolioName] = useState('Primo Portfolio');
  const [portfolioBaseCurrency, setPortfolioBaseCurrency] = useState('EUR');
  const [portfolioTimezone, setPortfolioTimezone] = useState(
    typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Rome' : 'Europe/Rome',
  );
  const [creatingPortfolio, setCreatingPortfolio] = useState(false);

  const selectedBroker = BROKER_OPTIONS.find((b) => b.value === broker);

  useEffect(() => {
    if (!opened) {
      return;
    }
    setResolvedPortfolioId(portfolioId);
  }, [opened, portfolioId]);

  const handleClose = () => {
    if (preview && step === 'preview') {
      cancelCsvImport(preview.batch_id).catch(() => {});
    }
    setStep('upload');
    setPreview(null);
    setResult(null);
    setError(null);
    setResolvedPortfolioId(portfolioId);
    onClose();
  };

  const handleCreatePortfolio = async () => {
    const name = portfolioName.trim();
    const baseCurrency = portfolioBaseCurrency.trim().toUpperCase();
    const timezone = portfolioTimezone.trim();

    if (!name) {
      setError('Nome portfolio obbligatorio');
      return;
    }
    if (!/^[A-Z]{3}$/.test(baseCurrency)) {
      setError('Valuta base non valida (es. EUR)');
      return;
    }
    if (!timezone) {
      setError('Timezone obbligatoria');
      return;
    }

    try {
      setCreatingPortfolio(true);
      setError(null);
      const created = await createPortfolio({
        name,
        base_currency: baseCurrency,
        timezone,
        cash_balance: 0,
      });
      setResolvedPortfolioId(created.id);
      onPortfolioCreated?.(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossibile creare il portfolio');
    } finally {
      setCreatingPortfolio(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!resolvedPortfolioId) {
      setError('Crea prima un portfolio per continuare con l’importazione');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await uploadCsvImportPreview(resolvedPortfolioId, file, broker);
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
      if (resolvedPortfolioId) {
        onImportComplete?.(resolvedPortfolioId);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleTemplateDownload = async () => {
    try {
      setDownloadingTemplate(true);
      setError(null);
      const { blob, filename } = await downloadCsvImportTemplate('generic');
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossibile scaricare il template');
    } finally {
      setDownloadingTemplate(false);
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
              leftSection={selectedBroker ? (
                <Avatar src={selectedBroker.logo} size={20} radius="sm" color={selectedBroker.logo ? undefined : 'blue'}>
                  {!selectedBroker.logo ? selectedBroker.label.slice(0, 1) : null}
                </Avatar>
              ) : undefined}
            />

            <Text size="sm" c="dimmed">
              Seleziona il file esportato dal tuo broker. Sono supportati i formati CSV e Excel (XLSX).
            </Text>

            {!resolvedPortfolioId && (
              <Card withBorder radius="lg" padding="md">
                <Stack gap="sm">
                  <Text fw={600}>Crea il tuo primo portfolio</Text>
                  <Text size="sm" c="dimmed">
                    Prima dell’import serve un portfolio di destinazione. Inserisci i dati minimi e poi continua con il file.
                  </Text>
                  <TextInput
                    label="Nome portfolio"
                    value={portfolioName}
                    onChange={(event) => setPortfolioName(event.currentTarget.value)}
                    placeholder="Es. Portafoglio principale"
                  />
                  <Group grow>
                    <TextInput
                      label="Valuta base"
                      value={portfolioBaseCurrency}
                      onChange={(event) => setPortfolioBaseCurrency(event.currentTarget.value.toUpperCase())}
                      placeholder="EUR"
                      maxLength={3}
                    />
                    <TextInput
                      label="Timezone"
                      value={portfolioTimezone}
                      onChange={(event) => setPortfolioTimezone(event.currentTarget.value)}
                      placeholder="Europe/Rome"
                    />
                  </Group>
                  <Group justify="flex-end">
                    <Button onClick={handleCreatePortfolio} loading={creatingPortfolio}>
                      Crea portfolio e continua
                    </Button>
                  </Group>
                </Stack>
              </Card>
            )}

            {resolvedPortfolioId && !preview && (
              <Alert color="teal" variant="light">
                Portafoglio esistente. Ora puoi caricare il file da importare.
              </Alert>
            )}

            {broker === 'generic' && (
              <Card withBorder radius="lg" padding="md">
                <Stack gap="md">
                  <div>
                    <Text fw={600}>Formato atteso per importazione generica</Text>
                    <Text size="sm" c="dimmed">
                      Il file generico deve contenere almeno le colonne obbligatorie. Puoi scaricare un file Excel vuoto di esempio e compilarlo.
                    </Text>
                  </div>

                  <div>
                    <Text size="sm" fw={600}>Colonne obbligatorie</Text>
                    <List size="sm" spacing={4}>
                      {GENERIC_REQUIRED_COLUMNS.map((column) => (
                        <List.Item key={column}>
                          <code>{column}</code>
                        </List.Item>
                      ))}
                    </List>
                  </div>

                  <div>
                    <Text size="sm" fw={600}>Colonne opzionali supportate</Text>
                    <List size="sm" spacing={4}>
                      {GENERIC_OPTIONAL_COLUMNS.map((column) => (
                        <List.Item key={column}>
                          <code>{column}</code>
                        </List.Item>
                      ))}
                    </List>
                  </div>

                  <Group justify="space-between" align="center">
                    <Text size="sm" c="dimmed">
                      Le date possono essere in formato <code>dd/mm/yyyy</code> o <code>yyyy-mm-dd</code>. Il campo <code>segno</code> usa <code>A</code> per acquisto e <code>V</code> per vendita.
                    </Text>
                    <Button variant="light" onClick={handleTemplateDownload} loading={downloadingTemplate}>
                      Scarica template XLSX
                    </Button>
                  </Group>
                </Stack>
              </Card>
            )}

            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              disabled={!resolvedPortfolioId}
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
