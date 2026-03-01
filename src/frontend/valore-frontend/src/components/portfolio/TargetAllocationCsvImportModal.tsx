import { useCallback, useRef, useState } from 'react';
import {
  Badge,
  Button,
  Group,
  Modal,
  Progress,
  Select,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconCheck, IconFileImport, IconX, IconAlertTriangle } from '@tabler/icons-react';
import {
  discoverAssets,
  ensureAsset,
  upsertPortfolioTargetAllocation,
  type AssetDiscoverItem,
} from '../../services/api';

interface Props {
  opened: boolean;
  onClose: () => void;
  portfolioId: number;
  onImportComplete?: () => void;
}

interface CsvRow {
  rowIndex: number;
  name: string;
  isin: string;
  weight: number;
}

type RowStatus = 'pending' | 'resolved' | 'ambiguous' | 'not_found';

interface ResolvedRow {
  csv: CsvRow;
  status: RowStatus;
  candidates: AssetDiscoverItem[];
  selectedCandidate: AssetDiscoverItem | null;
  manualSearchQuery: string;
  manualSearchResults: AssetDiscoverItem[];
  manualSearchLoading: boolean;
  importError: string | null;
}

type Step = 'upload' | 'preview' | 'importing' | 'done';

function parseCsvContent(text: string): CsvRow[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length === 0) return [];

  // Auto-detect header
  let startIndex = 0;
  const firstLine = lines[0].toLowerCase();
  if (
    firstLine.includes('nome') ||
    firstLine.includes('isin') ||
    firstLine.includes('peso') ||
    firstLine.includes('weight') ||
    firstLine.includes('name')
  ) {
    startIndex = 1;
  }

  const rows: CsvRow[] = [];
  for (let i = startIndex; i < lines.length; i++) {
    const parts = lines[i].split(/[,;]/).map((p) => p.trim());
    if (parts.length < 2) continue;

    let name = '';
    let isin = '';
    let weight = 0;

    if (parts.length === 2) {
      // Could be name,peso or isin,peso
      const lastVal = parseFloat(parts[1].replace(',', '.'));
      if (Number.isFinite(lastVal)) {
        const first = parts[0];
        if (/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(first)) {
          isin = first;
        } else {
          name = first;
        }
        weight = lastVal;
      }
    } else {
      name = parts[0];
      isin = parts[1];
      weight = parseFloat(parts[2].replace(',', '.'));
    }

    if (!Number.isFinite(weight) || weight < 0 || weight > 100) continue;
    if (!name && !isin) continue;

    rows.push({ rowIndex: i + 1, name, isin, weight });
  }
  return rows;
}

export function TargetAllocationCsvImportModal({
  opened,
  onClose,
  portfolioId,
  onImportComplete,
}: Props) {
  const [step, setStep] = useState<Step>('upload');
  const [resolvedRows, setResolvedRows] = useState<ResolvedRow[]>([]);
  const [resolving, setResolving] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [importProgress, setImportProgress] = useState(0);
  const [importTotal, setImportTotal] = useState(0);
  const [importResults, setImportResults] = useState<{ imported: number; errors: string[] }>({
    imported: 0,
    errors: [],
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const manualSearchTimers = useRef<Record<number, number>>({});

  const handleClose = () => {
    setStep('upload');
    setResolvedRows([]);
    setResolving(false);
    setParseError(null);
    setImportProgress(0);
    setImportTotal(0);
    setImportResults({ imported: 0, errors: [] });
    if (fileInputRef.current) fileInputRef.current.value = '';
    onClose();
  };

  const handleFileUpload = async (file: File) => {
    setParseError(null);
    const text = await file.text();
    const csvRows = parseCsvContent(text);

    if (csvRows.length === 0) {
      setParseError('Nessuna riga valida trovata nel CSV. Formato atteso: nome_titolo,isin,peso');
      return;
    }

    setResolving(true);
    const rows: ResolvedRow[] = [];

    for (const csv of csvRows) {
      const query = csv.isin || csv.name;
      let candidates: AssetDiscoverItem[] = [];
      try {
        candidates = await discoverAssets(query);
      } catch {
        // discovery failed
      }

      let status: RowStatus;
      let selectedCandidate: AssetDiscoverItem | null = null;

      if (candidates.length === 1) {
        status = 'resolved';
        selectedCandidate = candidates[0];
      } else if (candidates.length > 1) {
        // If we searched by ISIN, try to auto-match
        if (csv.isin) {
          const exactMatch = candidates.find(
            (c) => c.symbol === csv.isin || c.key?.includes(csv.isin),
          );
          if (exactMatch) {
            status = 'resolved';
            selectedCandidate = exactMatch;
          } else {
            status = 'ambiguous';
          }
        } else {
          status = 'ambiguous';
        }
      } else {
        status = 'not_found';
      }

      rows.push({
        csv,
        status,
        candidates,
        selectedCandidate,
        manualSearchQuery: '',
        manualSearchResults: [],
        manualSearchLoading: false,
        importError: null,
      });
    }

    setResolvedRows(rows);
    setResolving(false);
    setStep('preview');
  };

  const updateRow = useCallback((index: number, updates: Partial<ResolvedRow>) => {
    setResolvedRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...updates } : r)));
  }, []);

  const handleCandidateSelect = (index: number, key: string | null) => {
    const row = resolvedRows[index];
    if (!key) {
      updateRow(index, { selectedCandidate: null, status: 'ambiguous' });
      return;
    }
    const candidate = row.candidates.find((c) => c.key === key);
    if (candidate) {
      updateRow(index, { selectedCandidate: candidate, status: 'resolved' });
    }
  };

  const handleManualSearch = (index: number, query: string) => {
    updateRow(index, { manualSearchQuery: query });

    if (manualSearchTimers.current[index]) {
      window.clearTimeout(manualSearchTimers.current[index]);
    }

    const trimmed = query.trim();
    if (!trimmed) {
      updateRow(index, { manualSearchResults: [], manualSearchLoading: false });
      return;
    }

    updateRow(index, { manualSearchLoading: true });
    manualSearchTimers.current[index] = window.setTimeout(async () => {
      try {
        const results = await discoverAssets(trimmed);
        updateRow(index, { manualSearchResults: results, manualSearchLoading: false });
      } catch {
        updateRow(index, { manualSearchResults: [], manualSearchLoading: false });
      }
    }, 300);
  };

  const handleManualSelect = (index: number, key: string | null) => {
    if (!key) return;
    const row = resolvedRows[index];
    const candidate = row.manualSearchResults.find((c) => c.key === key);
    if (candidate) {
      updateRow(index, {
        selectedCandidate: candidate,
        status: 'resolved',
        candidates: [...row.candidates, candidate],
      });
    }
  };

  const resolvedCount = resolvedRows.filter((r) => r.status === 'resolved').length;
  const unresolvedCount = resolvedRows.filter((r) => r.status !== 'resolved').length;
  const totalWeightSum = resolvedRows.reduce((sum, r) => sum + r.csv.weight, 0);

  const canImport = resolvedCount > 0;

  const handleImport = async () => {
    const rowsToImport = resolvedRows.filter(
      (r) => r.status === 'resolved' && r.selectedCandidate,
    );
    setImportTotal(rowsToImport.length);
    setImportProgress(0);
    setStep('importing');

    let imported = 0;
    const errors: string[] = [];

    for (let i = 0; i < rowsToImport.length; i++) {
      const row = rowsToImport[i];
      const candidate = row.selectedCandidate!;

      try {
        let assetId = candidate.asset_id;

        if (!assetId || candidate.source !== 'db') {
          const ensured = await ensureAsset({
            source: candidate.source,
            asset_id: candidate.asset_id,
            symbol: candidate.symbol,
            name: candidate.name,
            exchange: candidate.exchange,
            provider: candidate.provider ?? 'yfinance',
            provider_symbol: candidate.provider_symbol ?? candidate.symbol,
            portfolio_id: portfolioId,
          });
          assetId = ensured.asset_id;
        }

        await upsertPortfolioTargetAllocation(portfolioId, {
          asset_id: assetId!,
          weight_pct: row.csv.weight,
        });
        imported++;
      } catch (err) {
        const label = row.csv.name || row.csv.isin;
        errors.push(`${label}: ${err instanceof Error ? err.message : String(err)}`);
      }

      setImportProgress(i + 1);
    }

    setImportResults({ imported, errors });
    onImportComplete?.();
    setStep('done');
  };

  const candidateLabel = (c: AssetDiscoverItem) =>
    `${c.symbol} - ${c.name ?? 'N/D'}${c.exchange ? ` (${c.exchange})` : ''}`;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="Importa Allocazione Target da CSV"
      size="xl"
    >
      <Stack>
        {step === 'upload' && (
          <>
            <Text size="sm" c="dimmed">
              Formato CSV atteso: <b>nome_titolo,isin,peso</b>
            </Text>
            <Text size="xs" c="dimmed">
              Almeno uno tra nome_titolo e isin deve essere presente. Il peso è un valore tra 0 e
              100. L'header è opzionale e viene rilevato automaticamente. Separatore: virgola o
              punto e virgola.
            </Text>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFileUpload(file);
              }}
              style={{ marginTop: 8 }}
            />
            {resolving && <Text size="sm">Analisi e risoluzione asset in corso...</Text>}
            {parseError && (
              <Text c="red" size="sm">
                {parseError}
              </Text>
            )}
          </>
        )}

        {step === 'preview' && (
          <>
            <Group>
              <Badge color="blue" size="lg">
                Totale: {resolvedRows.length}
              </Badge>
              <Badge color="green" size="lg">
                Risolti: {resolvedCount}
              </Badge>
              {unresolvedCount > 0 && (
                <Badge color="orange" size="lg">
                  Da risolvere: {unresolvedCount}
                </Badge>
              )}
            </Group>

            {totalWeightSum > 100 && (
              <Group gap="xs">
                <IconAlertTriangle size={16} color="orange" />
                <Text size="sm" c="orange" fw={500}>
                  Attenzione: il peso totale ({totalWeightSum.toFixed(2)}%) supera il 100%.
                </Text>
              </Group>
            )}

            <Table.ScrollContainer minWidth={600}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>#</Table.Th>
                    <Table.Th>Nome Titolo</Table.Th>
                    <Table.Th>ISIN</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Peso</Table.Th>
                    <Table.Th>Stato</Table.Th>
                    <Table.Th>Asset Risolto</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {resolvedRows.map((row, index) => (
                    <Table.Tr
                      key={row.csv.rowIndex}
                      bg={
                        row.status === 'resolved'
                          ? 'green.0'
                          : row.status === 'ambiguous'
                            ? 'yellow.0'
                            : 'red.0'
                      }
                    >
                      <Table.Td>{row.csv.rowIndex}</Table.Td>
                      <Table.Td>{row.csv.name || '-'}</Table.Td>
                      <Table.Td>{row.csv.isin || '-'}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>
                        {row.csv.weight.toFixed(2)}%
                      </Table.Td>
                      <Table.Td>
                        {row.status === 'resolved' && <IconCheck size={16} color="green" />}
                        {row.status === 'ambiguous' && (
                          <IconAlertTriangle size={16} color="orange" />
                        )}
                        {row.status === 'not_found' && <IconX size={16} color="red" />}
                      </Table.Td>
                      <Table.Td style={{ minWidth: 250 }}>
                        {row.status === 'resolved' && row.selectedCandidate && (
                          <Text size="sm">{candidateLabel(row.selectedCandidate)}</Text>
                        )}
                        {row.status === 'ambiguous' && (
                          <Select
                            size="xs"
                            placeholder="Scegli asset..."
                            data={row.candidates.map((c) => ({
                              value: c.key,
                              label: candidateLabel(c),
                            }))}
                            value={row.selectedCandidate?.key ?? null}
                            onChange={(val) => handleCandidateSelect(index, val)}
                          />
                        )}
                        {row.status === 'not_found' && (
                          <Select
                            size="xs"
                            placeholder="Cerca asset..."
                            data={row.manualSearchResults.map((c) => ({
                              value: c.key,
                              label: candidateLabel(c),
                            }))}
                            searchable
                            searchValue={row.manualSearchQuery}
                            onSearchChange={(val) => handleManualSearch(index, val)}
                            onChange={(val) => handleManualSelect(index, val)}
                            nothingFoundMessage={
                              row.manualSearchLoading ? 'Ricerca...' : 'Nessun risultato'
                            }
                          />
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            <Group justify="flex-end">
              <Button variant="outline" onClick={handleClose}>
                Annulla
              </Button>
              <Button
                onClick={handleImport}
                disabled={!canImport}
                leftSection={<IconFileImport size={16} />}
              >
                Importa {resolvedCount} asset
              </Button>
            </Group>
          </>
        )}

        {step === 'importing' && (
          <>
            <Text size="lg" fw={600}>
              Importazione in corso...
            </Text>
            <Progress
              value={importTotal > 0 ? (importProgress / importTotal) * 100 : 0}
              size="lg"
              animated
            />
            <Text size="sm" c="dimmed">
              {importProgress} / {importTotal} asset elaborati
            </Text>
          </>
        )}

        {step === 'done' && (
          <>
            <Text size="lg" fw={600} c="green">
              Importazione completata
            </Text>
            <Text>Asset importati: {importResults.imported}</Text>
            {importResults.errors.length > 0 && (
              <Stack gap="xs">
                <Text fw={500} c="red">
                  Errori:
                </Text>
                {importResults.errors.map((e, i) => (
                  <Text key={i} size="sm" c="red">
                    {e}
                  </Text>
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
