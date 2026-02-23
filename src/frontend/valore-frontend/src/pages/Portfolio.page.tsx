import { useEffect, useMemo, useState } from 'react';
import {
  Table,
  Button,
  Text,
  Group,
  Title,
  Card,
  SimpleGrid,
  Select,
  Alert,
  Loader,
  Drawer,
  Modal,
  Stack,
  NumberInput,
  ActionIcon,
  TextInput,
} from '@mantine/core';
import { IconEdit, IconPlus, IconTrash } from '@tabler/icons-react';
import {
  createPortfolio,
  deletePortfolio,
  deletePortfolioTargetAllocation,
  discoverAssets,
  ensureAsset,
  getAdminPortfolios,
  getPortfolioTargetAllocation,
  updatePortfolio,
  upsertPortfolioTargetAllocation,
} from '../services/api';
import type { AssetDiscoverItem, Portfolio, PortfolioTargetAllocationItem } from '../services/api';

const DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY = 'valore365.dashboard.selectedPortfolioId';

export function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null);
  const [allocations, setAllocations] = useState<PortfolioTargetAllocationItem[]>([]);
  const [loadingPortfolios, setLoadingPortfolios] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [drawerOpened, setDrawerOpened] = useState(false);
  const [formSaving, setFormSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [portfolioModalOpened, setPortfolioModalOpened] = useState(false);
  const [portfolioModalMode, setPortfolioModalMode] = useState<'create' | 'edit'>('create');
  const [portfolioDeleteOpened, setPortfolioDeleteOpened] = useState(false);
  const [portfolioSaving, setPortfolioSaving] = useState(false);
  const [portfolioDeleting, setPortfolioDeleting] = useState(false);
  const [portfolioFormError, setPortfolioFormError] = useState<string | null>(null);
  const [portfolioFormName, setPortfolioFormName] = useState('');
  const [portfolioFormBaseCurrency, setPortfolioFormBaseCurrency] = useState('EUR');
  const [portfolioFormTimezone, setPortfolioFormTimezone] = useState('Europe/Rome');

  const [targetWeight, setTargetWeight] = useState<number | string>(0);

  const [discoverQuery, setDiscoverQuery] = useState('');
  const [discoverItems, setDiscoverItems] = useState<AssetDiscoverItem[]>([]);
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [discoverSelectionKey, setDiscoverSelectionKey] = useState<string | null>(null);
  const [resolvedAssetId, setResolvedAssetId] = useState<number | null>(null);
  const [resolvedAssetLabel, setResolvedAssetLabel] = useState<string | null>(null);
  const [ensuringAsset, setEnsuringAsset] = useState(false);

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const loadTargetAllocation = async (portfolioId: number) => {
    const rows = await getPortfolioTargetAllocation(portfolioId);
    setAllocations(rows);
    return rows;
  };

  const loadPortfolios = async (preferredSelectedId?: string | null) => {
    const items = await getAdminPortfolios();
    setPortfolios(items);
    setSelectedPortfolioId((prev) => {
      const candidate = preferredSelectedId ?? prev;
      const exists = candidate ? items.some((p) => String(p.id) === candidate) : false;
      const nextSelected = exists ? candidate : (items[0] ? String(items[0].id) : null);
      if (typeof window !== 'undefined') {
        if (nextSelected) {
          window.localStorage.setItem(DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY, nextSelected);
        } else {
          window.localStorage.removeItem(DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY);
        }
      }
      return nextSelected;
    });
    return items;
  };

  const resetForm = () => {
    setTargetWeight(0);
    setDiscoverQuery('');
    setDiscoverItems([]);
    setDiscoverLoading(false);
    setDiscoverSelectionKey(null);
    setResolvedAssetId(null);
    setResolvedAssetLabel(null);
    setEnsuringAsset(false);
    setFormError(null);
    setFormSuccess(null);
  };

  useEffect(() => {
    let active = true;
    setLoadingPortfolios(true);
    setError(null);

    loadPortfolios()
      .then(() => {
        if (!active) return;
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento portafogli');
      })
      .finally(() => {
        if (active) setLoadingPortfolios(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedPortfolioId) {
      setAllocations([]);
      return;
    }
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    let active = true;
    setLoadingData(true);
    setError(null);

    loadTargetAllocation(portfolioId)
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento allocazione target');
      })
      .finally(() => {
        if (active) setLoadingData(false);
      });

    return () => {
      active = false;
    };
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (!drawerOpened) return;
    const q = discoverQuery.trim();
    if (!q) {
      setDiscoverItems([]);
      setDiscoverLoading(false);
      return;
    }

    let active = true;
    setDiscoverLoading(true);
    const timer = window.setTimeout(() => {
      discoverAssets(q)
        .then((items) => {
          if (active) setDiscoverItems(items);
        })
        .catch(() => {
          if (active) setDiscoverItems([]);
        })
        .finally(() => {
          if (active) setDiscoverLoading(false);
        });
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [discoverQuery, drawerOpened]);

  const totalWeight = useMemo(
    () => allocations.reduce((sum, item) => sum + item.weight_pct, 0),
    [allocations],
  );

  const openDrawer = () => {
    resetForm();
    setDrawerOpened(true);
  };

  const openCreatePortfolioModal = () => {
    setPortfolioModalMode('create');
    setPortfolioFormName('');
    setPortfolioFormBaseCurrency('EUR');
    setPortfolioFormTimezone('Europe/Rome');
    setPortfolioFormError(null);
    setPortfolioModalOpened(true);
  };

  const openEditPortfolioModal = () => {
    if (!selectedPortfolio) return;
    setPortfolioModalMode('edit');
    setPortfolioFormName(selectedPortfolio.name);
    setPortfolioFormBaseCurrency(selectedPortfolio.base_currency);
    setPortfolioFormTimezone(selectedPortfolio.timezone);
    setPortfolioFormError(null);
    setPortfolioModalOpened(true);
  };

  const handleSavePortfolio = async () => {
    setPortfolioFormError(null);
    const name = portfolioFormName.trim();
    const baseCurrency = portfolioFormBaseCurrency.trim().toUpperCase();
    const timezone = portfolioFormTimezone.trim();
    if (!name) {
      setPortfolioFormError('Nome portfolio obbligatorio');
      return;
    }
    if (!/^[A-Z]{3}$/.test(baseCurrency)) {
      setPortfolioFormError('Valuta base non valida (es. EUR)');
      return;
    }
    if (!timezone) {
      setPortfolioFormError('Timezone obbligatoria');
      return;
    }

    try {
      setPortfolioSaving(true);
      if (portfolioModalMode === 'create') {
        const created = await createPortfolio({
          name,
          base_currency: baseCurrency,
          timezone,
        });
        await loadPortfolios(String(created.id));
        setFormSuccess(`Portfolio "${created.name}" creato`);
      } else {
        const portfolioId = Number(selectedPortfolioId);
        if (!Number.isFinite(portfolioId)) {
          setPortfolioFormError('Seleziona un portfolio valido');
          return;
        }
        const updated = await updatePortfolio(portfolioId, {
          name,
          base_currency: baseCurrency,
          timezone,
        });
        await loadPortfolios(String(updated.id));
        setFormSuccess(`Portfolio "${updated.name}" aggiornato`);
      }
      setPortfolioModalOpened(false);
    } catch (err) {
      setPortfolioFormError(err instanceof Error ? err.message : 'Errore salvataggio portfolio');
    } finally {
      setPortfolioSaving(false);
    }
  };

  const handleDeletePortfolio = async () => {
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

    try {
      setPortfolioDeleting(true);
      await deletePortfolio(portfolioId);
      await loadPortfolios(null);
      setPortfolioDeleteOpened(false);
      setFormSuccess('Portfolio eliminato');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore eliminazione portfolio');
    } finally {
      setPortfolioDeleting(false);
    }
  };

  const handleDiscoverSelection = async (value: string | null) => {
    setDiscoverSelectionKey(value);
    setFormError(null);
    setFormSuccess(null);
    setResolvedAssetId(null);
    setResolvedAssetLabel(null);

    if (!value) return;
    const selected = discoverItems.find((item) => item.key === value);
    if (!selected) return;

    const label = `${selected.symbol} - ${selected.name ?? 'N/D'}${selected.exchange ? ` (${selected.exchange})` : ''}`;

    if (selected.source === 'db' && selected.asset_id) {
      setResolvedAssetId(selected.asset_id);
      setResolvedAssetLabel(label);
      return;
    }

    try {
      setEnsuringAsset(true);
      const portfolioId = Number(selectedPortfolioId);
      const ensured = await ensureAsset({
        source: selected.source,
        asset_id: selected.asset_id,
        symbol: selected.symbol,
        name: selected.name,
        exchange: selected.exchange,
        provider: selected.provider ?? 'twelvedata',
        provider_symbol: selected.provider_symbol ?? selected.symbol,
        portfolio_id: Number.isFinite(portfolioId) ? portfolioId : undefined,
      });
      setResolvedAssetId(ensured.asset_id);
      setResolvedAssetLabel(label);
      if (ensured.created) {
        setFormSuccess(`Asset ${ensured.symbol} creato e selezionato.`);
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Errore nella risoluzione asset');
    } finally {
      setEnsuringAsset(false);
    }
  };

  const handleSaveTargetWeight = async () => {
    setFormError(null);
    setFormSuccess(null);
    const portfolioId = Number(selectedPortfolioId);
    const normalizedWeight = typeof targetWeight === 'number' ? targetWeight : Number(targetWeight);

    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setFormError('Seleziona un portfolio valido');
      return;
    }
    if (!resolvedAssetId) {
      setFormError('Seleziona un asset dalla ricerca');
      return;
    }
    if (!Number.isFinite(normalizedWeight) || normalizedWeight < 0 || normalizedWeight > 100) {
      setFormError('Il peso deve essere tra 0 e 100');
      return;
    }

    try {
      setFormSaving(true);
      await upsertPortfolioTargetAllocation(portfolioId, {
        asset_id: resolvedAssetId,
        weight_pct: normalizedWeight,
      });
      await loadTargetAllocation(portfolioId);
      setDrawerOpened(false);
      resetForm();
      setFormSuccess('Peso salvato correttamente');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Errore salvataggio peso');
    } finally {
      setFormSaving(false);
    }
  };

  const handleDeleteAllocation = async (assetIdToDelete: number) => {
    const portfolioId = Number(selectedPortfolioId);
    if (!portfolioId) return;
    setError(null);
    try {
      await deletePortfolioTargetAllocation(portfolioId, assetIdToDelete);
      await loadTargetAllocation(portfolioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore rimozione asset dal portafoglio');
    }
  };

  const rows = allocations.map((item) => (
    <Table.Tr key={item.asset_id}>
      <Table.Td>
        <Text fw={500}>{item.symbol}</Text>
        <Text size="xs" c="dimmed">{item.name}</Text>
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{item.weight_pct.toFixed(2)}%</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>
        <ActionIcon color="red" variant="light" onClick={() => handleDeleteAllocation(item.asset_id)} aria-label={`Rimuovi ${item.symbol}`}>
          <IconTrash size={16} />
        </ActionIcon>
      </Table.Td>
    </Table.Tr>
  ));

  const discoverOptions = discoverItems.map((item) => ({
    value: item.key,
    label:
      `${item.symbol} - ${item.name ?? 'N/D'}${item.exchange ? ` (${item.exchange})` : ''}` +
      (item.source === 'db' ? ' [DB]' : ' [Provider]'),
  }));

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2} fw={700}>Il Mio Portafoglio</Title>
        <Group gap="xs">
          <Button variant="default" onClick={openCreatePortfolioModal}>
            Nuovo Portfolio
          </Button>
          <Button leftSection={<IconEdit size={16} />} variant="default" onClick={openEditPortfolioModal} disabled={!selectedPortfolioId}>
            Modifica
          </Button>
          <Button color="red" variant="light" onClick={() => setPortfolioDeleteOpened(true)} disabled={!selectedPortfolioId}>
            Elimina
          </Button>
          <Button leftSection={<IconPlus size={18} />} variant="light" onClick={openDrawer} disabled={!selectedPortfolioId}>
            Aggiungi Asset / Peso
          </Button>
        </Group>
      </Group>

      <Group align="end" mb="md">
        <Select
          label="Portfolio"
          placeholder={loadingPortfolios ? 'Caricamento...' : 'Seleziona portfolio'}
          data={portfolios.map((p) => ({ value: String(p.id), label: `${p.name} (#${p.id})` }))}
          value={selectedPortfolioId}
          onChange={setSelectedPortfolioId}
          disabled={loadingPortfolios || portfolios.length === 0}
          w={360}
        />
        {(loadingPortfolios || loadingData) && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>

      {error && <Alert color="red" mb="md">{error}</Alert>}
      {formSuccess && <Alert color="teal" mb="md">{formSuccess}</Alert>}

      <SimpleGrid cols={{ base: 1, md: 3 }} mb="lg">
        <Card withBorder>
          <Text size="sm" c="dimmed">Asset in portfolio</Text>
          <Text fw={700} size="xl">{allocations.length}</Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Peso totale assegnato</Text>
          <Text fw={700} size="xl">{totalWeight.toFixed(2)}%</Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Peso residuo</Text>
          <Text fw={700} size="xl" c={totalWeight > 100 ? 'red' : 'teal'}>
            {(100 - totalWeight).toFixed(2)}%
          </Text>
        </Card>
      </SimpleGrid>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Asset</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Peso Target</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Azioni</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.length ? rows : (
            <Table.Tr>
              <Table.Td colSpan={3}>
                <Text c="dimmed" ta="center">
                  {selectedPortfolioId ? 'Nessun asset assegnato al portafoglio' : 'Nessun portafoglio disponibile'}
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>

      <Modal
        opened={portfolioModalOpened}
        onClose={() => setPortfolioModalOpened(false)}
        title={portfolioModalMode === 'create' ? 'Nuovo Portfolio' : 'Modifica Portfolio'}
        centered
      >
        <Stack>
          {portfolioFormError && <Alert color="red">{portfolioFormError}</Alert>}
          <TextInput
            label="Nome"
            value={portfolioFormName}
            onChange={(event) => setPortfolioFormName(event.currentTarget.value)}
            placeholder="Es. Portafoglio ETF"
          />
          <TextInput
            label="Valuta Base"
            value={portfolioFormBaseCurrency}
            onChange={(event) => setPortfolioFormBaseCurrency(event.currentTarget.value.toUpperCase())}
            placeholder="EUR"
            maxLength={3}
          />
          <TextInput
            label="Timezone"
            value={portfolioFormTimezone}
            onChange={(event) => setPortfolioFormTimezone(event.currentTarget.value)}
            placeholder="Europe/Rome"
          />
          <Button onClick={handleSavePortfolio} loading={portfolioSaving}>
            {portfolioModalMode === 'create' ? 'Crea Portfolio' : 'Salva Modifiche'}
          </Button>
        </Stack>
      </Modal>

      <Modal
        opened={portfolioDeleteOpened}
        onClose={() => setPortfolioDeleteOpened(false)}
        title="Conferma eliminazione portfolio"
        centered
      >
        <Stack>
          <Text size="sm">
            Vuoi eliminare il portfolio {selectedPortfolio ? `"${selectedPortfolio.name}"` : ''}?
          </Text>
          <Text size="sm" c="dimmed">
            Verranno rimossi anche i pesi target e le eventuali transazioni collegate.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPortfolioDeleteOpened(false)} disabled={portfolioDeleting}>
              Annulla
            </Button>
            <Button color="red" onClick={handleDeletePortfolio} loading={portfolioDeleting}>
              Elimina Portfolio
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Drawer opened={drawerOpened} onClose={() => setDrawerOpened(false)} title="Aggiungi Asset al Portafoglio" position="right" size="md">
        <Stack>
          {formError && <Alert color="red">{formError}</Alert>}
          {formSuccess && <Alert color="teal">{formSuccess}</Alert>}

          <Select
            searchable
            label="Cerca asset (DB + provider)"
            placeholder="Scrivi simbolo o nome (es. AAPL, VWCE, Apple)"
            searchValue={discoverQuery}
            onSearchChange={setDiscoverQuery}
            value={discoverSelectionKey}
            onChange={(value) => {
              void handleDiscoverSelection(value);
            }}
            data={discoverOptions}
            nothingFoundMessage={discoverQuery.trim() ? 'Nessun risultato' : 'Inizia a digitare'}
            rightSection={discoverLoading || ensuringAsset ? <Loader size="xs" /> : null}
            clearable
          />

          <Text size="sm" c="dimmed">
            {resolvedAssetLabel ? `Asset selezionato: ${resolvedAssetLabel}` : 'Seleziona un asset dalla ricerca'}
          </Text>

          <NumberInput
            label="Peso target (%)"
            value={targetWeight}
            onChange={setTargetWeight}
            min={0}
            max={100}
            decimalScale={2}
            suffix="%"
          />

          <Button onClick={handleSaveTargetWeight} loading={formSaving || ensuringAsset}>
            Aggiungi al Portafoglio
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
