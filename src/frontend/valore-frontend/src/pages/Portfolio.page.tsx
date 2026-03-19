import { useState } from 'react';
import {
  Table,
  Card,
  Button,
  Text,
  Group,
  Alert,
  Loader,
  ActionIcon,
  Tabs,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { IconEdit, IconPlus, IconTrash, IconArrowsExchange, IconTarget, IconCopy, IconFileImport, IconCoins, IconChartArrows, IconSettings2, IconRobot, IconInfoCircle, IconWallet } from '@tabler/icons-react';
import { CashSection } from '../components/portfolio/sections/CashSection.tsx';
import { CsvImportModal } from '../components/portfolio/modals/CsvImportModal.tsx';
import { TargetAllocationCsvImportModal } from '../components/portfolio/modals/TargetAllocationCsvImportModal.tsx';
import { PacRuleDrawer } from '../components/portfolio/drawers/PacRuleDrawer.tsx';
import { PacSection } from '../components/portfolio/sections/PacSection.tsx';
import { MobileActionSheet } from '../components/mobile/MobileActionSheet.tsx';
import { MobileBottomNav } from '../components/mobile/MobileBottomNav.tsx';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher.tsx';
import { TargetAllocationSection } from '../components/portfolio/sections/TargetAllocationSection.tsx';
import { TransactionsSection } from '../components/portfolio/sections/TransactionsSection.tsx';
import { ENABLE_TARGET_ALLOCATION } from '../features';
import { formatNum, formatMoneyOrNA, formatDateTime, formatTransactionSideLabel, getTransactionSideColor } from '../components/dashboard/formatters';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';

import { usePortfolioPage } from '../components/portfolio/hooks/usePortfolioPage';
import { usePortfolioSummary } from '../components/dashboard/hooks/queries';
import { RebalancePreviewModal } from '../components/portfolio/modals/RebalancePreviewModal';
import { PortfolioModal, PortfolioCloneModal, PortfolioDeleteModal, EditTransactionModal, DeleteTransactionModal } from '../components/portfolio/modals/PortfolioFormModals';
import { TransactionDrawer } from '../components/portfolio/drawers/TransactionDrawer';
import { TargetAllocationDrawer } from '../components/portfolio/drawers/TargetAllocationDrawer';
import { PortfolioEmptyState } from '../components/portfolio/sections/PortfolioEmptyState';
import { TransactionMobileCard } from '../components/portfolio/TransactionMobileCard';
import { AssetInfoModal } from '../components/dashboard/holdings/AssetInfoModal';

export function PortfolioPage() {
  const s = usePortfolioPage();
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const portfolioId = s.selectedPortfolioId ? Number(s.selectedPortfolioId) : null;
  const { data: summary } = usePortfolioSummary(portfolioId);
  const [assetInfoModal, setAssetInfoModal] = useState<{ assetId: number; symbol: string } | null>(null);

  // --- Allocation table rows ---
  const allocationRows = s.allocations.map((item) => (
    <Table.Tr key={item.asset_id}>
      <Table.Td>
        <Text fw={500}>{item.symbol}</Text>
        <Text size="xs" c="dimmed">{item.name}</Text>
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{formatNum(item.weight_pct)}%</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>
        {s.portfolioTargetNotional != null
          ? formatMoneyOrNA((s.portfolioTargetNotional * item.weight_pct) / 100, s.selectedPortfolio?.base_currency)
          : 'N/D'}
      </Table.Td>
      {!s.isMobile && (
        <Table.Td style={{ textAlign: 'right' }}>
          <ActionIcon color="red" variant="light" onClick={() => s.handleDeleteAllocation(item.asset_id)} aria-label={`Rimuovi ${item.symbol}`}>
            <IconTrash size={16} />
          </ActionIcon>
        </Table.Td>
      )}
    </Table.Tr>
  ));

  const allocationMobileCards = s.allocations.map((item) => {
    const targetValue = s.portfolioTargetNotional != null
      ? formatMoneyOrNA((s.portfolioTargetNotional * item.weight_pct) / 100, s.selectedPortfolio?.base_currency)
      : 'N/D';
    return (
      <Card key={`allocation-mobile-${item.asset_id}`} withBorder>
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <div>
            <Text fw={600}>{item.symbol}</Text>
            <Text size="xs" c="dimmed">{item.name}</Text>
          </div>
          <Text fw={700}>{formatNum(item.weight_pct)}%</Text>
        </Group>
        <Group justify="space-between" mt="sm" gap="xs">
          <Text size="sm" c="dimmed">Controvalore target</Text>
          <Text size="sm" fw={600}>{targetValue}</Text>
        </Group>
      </Card>
    );
  });

  // --- Transaction table rows ---
  const transactionRows = s.sortedTransactions.map((tx) => {
    const gross = tx.quantity * tx.price;
    const total = tx.side === 'buy' ? gross + (tx.fees ?? 0) + (tx.taxes ?? 0) : gross - (tx.fees ?? 0) - (tx.taxes ?? 0);
    return (
      <Table.Tr key={tx.id}>
        <Table.Td>{formatDateTime(tx.trade_at)}</Table.Td>
        <Table.Td>
          <Text fw={600} c={getTransactionSideColor(tx.side)}>
            {formatTransactionSideLabel(tx.side)}
          </Text>
        </Table.Td>
        <Table.Td>
          <Group gap={4} wrap="nowrap">
            <div>
              <Text fw={500}>{tx.symbol}</Text>
              {tx.asset_name ? <Text size="xs" c="dimmed">{tx.asset_name}</Text> : null}
            </div>
            {tx.asset_id != null && (
              <Tooltip label="Dettaglio asset" withArrow>
                <UnstyledButton onClick={() => setAssetInfoModal({ assetId: tx.asset_id!, symbol: tx.symbol })}>
                  <IconInfoCircle size={16} stroke={1.5} style={{ opacity: 0.5 }} />
                </UnstyledButton>
              </Tooltip>
            )}
          </Group>
        </Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">{formatNum(tx.quantity, 4)}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="sm">{formatMoneyOrNA(tx.price, tx.trade_currency)}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }} visibleFrom="md">{formatMoneyOrNA(tx.fees ?? 0, tx.trade_currency)}</Table.Td>
        <Table.Td style={{ textAlign: 'right' }}>{formatMoneyOrNA(total, tx.trade_currency)}</Table.Td>
        {!s.isMobile && (
          <Table.Td style={{ textAlign: 'right' }}>
            <Group gap={6} justify="flex-end" wrap="nowrap" style={{ minWidth: 74 }}>
              <ActionIcon color="blue" variant="light" onClick={() => s.openEditTransactionModal(tx)} aria-label={`Modifica transazione ${tx.id}`}>
                <IconEdit size={16} />
              </ActionIcon>
              <ActionIcon color="red" variant="light" onClick={() => s.openDeleteTransactionModal(tx)} loading={s.deletingTransactionId === tx.id} aria-label={`Elimina transazione ${tx.id}`}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          </Table.Td>
        )}
      </Table.Tr>
    );
  });

  // --- Transaction mobile cards (using reusable component) ---
  const transactionMobileCards = s.sortedTransactions.map((tx) => (
    <TransactionMobileCard
      key={`tx-mobile-${tx.id}`}
      id={tx.id}
      symbol={tx.symbol}
      assetName={tx.asset_name}
      side={tx.side}
      tradeAt={tx.trade_at}
      quantity={tx.quantity}
      price={tx.price}
      fees={tx.fees ?? 0}
      taxes={tx.taxes ?? 0}
      tradeCurrency={tx.trade_currency}
      notes={tx.notes}
      deleting={s.deletingTransactionId === tx.id}
      onEdit={() => s.openEditTransactionModal(tx)}
      onDelete={() => s.openDeleteTransactionModal(tx)}
    />
  ));

  // --- Totals row ---
  if (s.sortedTransactions.length > 0) {
    transactionRows.push(
      <Table.Tr key="transactions-total" style={{ fontWeight: 700, borderTop: '2px solid var(--mantine-color-dark-4)' }}>
        <Table.Td><Text fw={700} size="sm">TOTALE</Text></Table.Td>
        <Table.Td /><Table.Td />
        <Table.Td visibleFrom="sm" /><Table.Td visibleFrom="sm" />
        <Table.Td visibleFrom="md" style={{ textAlign: 'right' }}>
          {s.transactionTotals.mixedCurrencies ? (
            <Text fw={700} size="sm" c="dimmed">—</Text>
          ) : (
            <Text fw={700} size="sm">
              {formatMoneyOrNA(s.transactionTotals.totalFees, s.transactionTotals.currency ?? s.selectedPortfolio?.base_currency)}
            </Text>
          )}
        </Table.Td>
        <Table.Td style={{ textAlign: 'right' }}>
          {s.transactionTotals.mixedCurrencies ? (
            <Text fw={700} size="sm" c="dimmed">Valute miste</Text>
          ) : (
            <Text fw={700} size="sm">
              {formatMoneyOrNA(s.transactionTotals.totalValue, s.transactionTotals.currency ?? s.selectedPortfolio?.base_currency)}
            </Text>
          )}
        </Table.Td>
        {!s.isMobile && <Table.Td />}
      </Table.Tr>,
    );

    transactionMobileCards.push(
      <Card
        key="tx-mobile-total"
        radius="xl"
        p="lg"
        style={{
          background: isDark
            ? `linear-gradient(135deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 100%)`
            : 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          color: '#ffffff',
          boxShadow: isDark ? '0 18px 36px rgba(0, 0, 0, 0.32)' : '0 18px 36px rgba(15, 23, 42, 0.20)',
        }}
      >
        <Group justify="space-between" gap="xs">
          <Text fw={700} c="rgba(255,255,255,0.75)">Totale filtro</Text>
          {s.transactionTotals.mixedCurrencies ? (
            <Text fw={700} c="rgba(255,255,255,0.75)">Valute miste</Text>
          ) : (
            <Text fw={700}>
              {formatMoneyOrNA(s.transactionTotals.totalValue, s.transactionTotals.currency ?? s.selectedPortfolio?.base_currency)}
            </Text>
          )}
        </Group>
      </Card>,
    );
  }

  const mobileTabItems = ENABLE_TARGET_ALLOCATION
    ? [{ value: 'target', label: 'Target', icon: IconTarget }]
    : [];

  return (
    <>
      <PageLayout mobileBottomPadding={s.isMobile ? 180 : undefined} style={s.isMobile ? { paddingTop: 4 } : undefined}>
      <PageHeader
        eyebrow="Gestione movimenti, liquidita e target"
        title="Portfolio"
        description="Operazioni, allocazione e struttura del portafoglio in una vista operativa unica."
        actions={(
          <PortfolioSwitcher
            portfolios={s.portfolios}
            value={s.selectedPortfolioId}
            selectedPortfolioCashBalance={summary?.cash_balance ?? null}
            onChange={(nextValue) => s.setSelectedPortfolioId(nextValue)}
            loading={s.loadingPortfolios}
            style={s.isMobile ? { width: '100%' } : { width: '100%', maxWidth: 360 }}
            onCreatePortfolio={s.openCreatePortfolioModal}
            onEditPortfolio={s.selectedPortfolioId ? s.openEditPortfolioModal : null}
            onClonePortfolio={s.selectedPortfolioId ? s.openClonePortfolioModal : null}
            onDeletePortfolio={s.selectedPortfolioId ? () => s.setPortfolioDeleteOpened(true) : null}
          />
        )}
      />

      <Group mb={s.isMobile ? 'xs' : 'md'} align="flex-end" gap="xs">
        {(s.loadingPortfolios || s.loadingData) && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>

      <Group mb={s.isMobile ? 'xs' : 'md'} justify="space-between" wrap="wrap" gap="xs">
        <Tabs
          value={s.portfolioView}
          onChange={(value) => {
            const next = (value as 'transactions' | 'target' | 'pac' | 'cash') ?? 'transactions';
            s.setPortfolioView(!ENABLE_TARGET_ALLOCATION && next === 'target' ? 'transactions' : next);
          }}
          variant="default"
          style={s.isMobile ? { width: '100%' } : undefined}
        >
          {!s.isMobile && (
            <Tabs.List style={{ flexWrap: 'nowrap', overflowX: 'auto', overflowY: 'hidden', WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none', paddingBottom: 0, gap: 0 }}>
              <Tabs.Tab value="transactions" leftSection={<IconArrowsExchange size={16} />}>
                <Text span>Transazioni</Text>
              </Tabs.Tab>
              {ENABLE_TARGET_ALLOCATION && (
                <Tabs.Tab value="target" leftSection={<IconTarget size={16} />}>
                  <Text span>Allocazione target</Text>
                </Tabs.Tab>
              )}
              <Tabs.Tab value="cash" leftSection={<IconWallet size={16} />}>
                <Text span>Liquidità</Text>
              </Tabs.Tab>
              <Tabs.Tab value="pac" leftSection={<IconCoins size={16} />}>
                <Text span>Piano di Accumulo</Text>
              </Tabs.Tab>
            </Tabs.List>
          )}
        </Tabs>
        {s.portfolioView === 'transactions' && !s.isMobile && (
          <Group gap="xs">
            <Button leftSection={<IconPlus size={16} />} onClick={() => s.setTransactionDrawerOpened(true)} disabled={!s.selectedPortfolioId}>
              Nuova Transazione
            </Button>
            <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => s.setCsvImportOpened(true)}>
              Importa
            </Button>
          </Group>
        )}
        {ENABLE_TARGET_ALLOCATION && s.portfolioView === 'target' && !s.isMobile && (
          <Button variant="light" leftSection={<IconTarget size={16} />} onClick={s.rebalance.openPreviewModal} disabled={!s.selectedPortfolioId}>
            Genera da target
          </Button>
        )}
        {s.portfolioView === 'pac' && !s.isMobile && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => { s.setEditingPacRule(null); s.setPacDrawerOpened(true); }} disabled={!s.selectedPortfolioId}>
            Nuova regola PAC
          </Button>
        )}
      </Group>

      {s.error && <Alert color="red" mb="md">{s.error}</Alert>}
      {s.transactionsError && <Alert color="red" mb="md">{s.transactionsError}</Alert>}
      {s.formSuccess && <Alert color="teal" mb="md">{s.formSuccess}</Alert>}

      {s.portfolios.length === 0 && (
        <PortfolioEmptyState
          onCreatePortfolio={s.openCreatePortfolioModal}
          onImportFromFile={() => s.setCsvImportOpened(true)}
        />
      )}

      {ENABLE_TARGET_ALLOCATION && s.portfolioView === 'target' && (
        <TargetAllocationSection
          allocationsCount={s.allocations.length}
          totalWeight={s.totalWeight}
          portfolioTargetNotionalLabel={formatMoneyOrNA(s.portfolioTargetNotional, s.selectedPortfolio?.base_currency)}
          assignedTargetValueLabel={s.assignedTargetValue != null ? formatMoneyOrNA(s.assignedTargetValue, s.selectedPortfolio?.base_currency) : null}
          selectedPortfolioId={s.selectedPortfolioId}
          rows={allocationRows}
          mobileCards={allocationMobileCards}
          hasRows={s.allocations.length > 0}
          onOpenAddAssetWeight={() => s.setDrawerOpened(true)}
          onOpenCsvImport={() => s.setTargetCsvImportOpened(true)}
          showActions={!s.isMobile}
        />
      )}

      {s.portfolioView === 'transactions' && (
        <TransactionsSection
          loading={s.loadingTransactions}
          filterQuery={s.transactionFilterQuery}
          onFilterQueryChange={s.setTransactionFilterQuery}
          filterSide={s.transactionFilterSide}
          onFilterSideChange={s.setTransactionFilterSide}
          sortKey={s.transactionSortKey}
          onSortKeyChange={(value) => s.setTransactionSortKey((value as 'trade_at' | 'symbol' | 'side' | 'value') ?? 'trade_at')}
          sortDir={s.transactionSortDir}
          onSortDirChange={(value) => s.setTransactionSortDir((value as 'asc' | 'desc') ?? 'desc')}
          rows={transactionRows}
          mobileCards={transactionMobileCards}
          hasRows={s.sortedTransactions.length > 0}
          selectedPortfolioId={s.selectedPortfolioId}
          showActions={!s.isMobile}
        />
      )}

      {s.portfolioView === 'cash' && s.selectedPortfolioId && (
        <CashSection selectedPortfolioId={s.selectedPortfolioId} baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'} />
      )}

      {s.portfolioView === 'pac' && s.selectedPortfolioId && (
        <PacSection
          selectedPortfolioId={s.selectedPortfolioId}
          baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'}
          onOpenPacDrawer={() => { s.setEditingPacRule(null); s.setPacDrawerOpened(true); }}
          onEditPacRule={(rule) => { s.setEditingPacRule(rule); s.setPacDrawerOpened(true); }}
          refreshTrigger={s.pacRefreshTrigger}
        />
      )}
      </PageLayout>

      {s.isMobile && (
        <MobileBottomNav
          items={mobileTabItems}
          value={s.portfolioView === 'target' ? 'target' : null}
          bottomOffset={86}
          onChange={(value) => {
            if (value === 'target' && ENABLE_TARGET_ALLOCATION) {
              s.setPortfolioView((current) => (current === 'target' ? 'transactions' : 'target'));
            }
          }}
        />
      )}

      {s.isMobile && (
        <MobileActionSheet
          opened={s.mobileActionSheetOpened}
          onOpen={() => s.setMobileActionSheetOpened(true)}
          onClose={() => s.setMobileActionSheetOpened(false)}
          title="Azioni portfolio"
          bottomOffset={12}
          badge={s.selectedPortfolio ? s.selectedPortfolio.name : 'Seleziona portafoglio'}
          primaryAction={{
            label: s.portfolioView === 'target' ? 'Aggiungi asset' : s.portfolioView === 'pac' ? 'Nuova regola PAC' : 'Nuova transazione',
            onClick: s.portfolioView === 'target' ? () => s.setDrawerOpened(true) : s.portfolioView === 'pac' ? () => { s.setEditingPacRule(null); s.setPacDrawerOpened(true); } : () => s.setTransactionDrawerOpened(true),
            disabled: !s.selectedPortfolioId,
          }}
          items={[
            { label: 'Nuova transazione', description: 'Apri il drawer rapido per acquisti e vendite', icon: IconArrowsExchange, onClick: () => s.setTransactionDrawerOpened(true), disabled: !s.selectedPortfolioId },
            { label: 'Importa', description: 'Carica movimenti o storico dal file broker', icon: IconFileImport, onClick: () => s.setCsvImportOpened(true), disabled: s.portfolioView !== 'transactions' },
            { label: 'Aggiungi asset target', description: 'Inserisci un nuovo peso target nel portafoglio', icon: IconTarget, onClick: () => s.setDrawerOpened(true), disabled: !s.selectedPortfolioId || !ENABLE_TARGET_ALLOCATION || s.portfolioView !== 'target' },
            { label: 'Genera da target', description: 'Preview di ribilanciamento disponibile su desktop', icon: IconChartArrows, onClick: () => s.setFormSuccess('La preview di ribilanciamento e disponibile solo su desktop'), disabled: !s.selectedPortfolioId || !ENABLE_TARGET_ALLOCATION || s.portfolioView !== 'target' },
            { label: 'Nuovo portfolio', description: 'Crea un nuovo contenitore con valuta e cash dedicati', icon: IconPlus, onClick: s.openCreatePortfolioModal },
            { label: 'Clona portfolio', description: 'Duplica impostazioni e target allocation', icon: IconCopy, onClick: s.openClonePortfolioModal, disabled: !s.selectedPortfolioId },
            { label: 'Liquidità', description: 'Gestisci la liquidità del portafoglio', icon: IconWallet, onClick: () => { s.setPortfolioView('cash'); s.setMobileActionSheetOpened(false); }, disabled: !s.selectedPortfolioId },
            { label: 'Piano di Accumulo', description: 'Visualizza e gestisci le regole PAC', icon: IconCoins, onClick: () => { s.setPortfolioView('pac'); s.setMobileActionSheetOpened(false); }, disabled: !s.selectedPortfolioId },
            { label: 'Modifica portfolio', description: 'Aggiorna nome, valuta base, timezone e cash', icon: IconSettings2, onClick: s.openEditPortfolioModal, disabled: !s.selectedPortfolioId },
          ]}
        />
      )}

      {/* --- Modals & Drawers --- */}

      <PortfolioModal
        opened={s.portfolioModalOpened} onClose={() => s.setPortfolioModalOpened(false)} mode={s.portfolioModalMode}
        formError={s.portfolioFormError} formName={s.portfolioFormName} onFormNameChange={s.setPortfolioFormName}
        formBaseCurrency={s.portfolioFormBaseCurrency} onFormBaseCurrencyChange={s.setPortfolioFormBaseCurrency}
        formTimezone={s.portfolioFormTimezone} onFormTimezoneChange={s.setPortfolioFormTimezone}
        formTargetNotional={s.portfolioFormTargetNotional} onFormTargetNotionalChange={s.setPortfolioFormTargetNotional}
        saving={s.portfolioSaving} onSave={s.handleSavePortfolio}
      />

      <PortfolioCloneModal
        opened={s.portfolioCloneOpened} onClose={() => s.setPortfolioCloneOpened(false)}
        cloneName={s.portfolioCloneName} onCloneNameChange={s.setPortfolioCloneName}
        cloneError={s.portfolioCloneError} cloning={s.portfolioCloning} onClone={s.handleClonePortfolio}
      />

      <PortfolioDeleteModal
        opened={s.portfolioDeleteOpened} onClose={() => s.setPortfolioDeleteOpened(false)}
        selectedPortfolio={s.selectedPortfolio} deleting={s.portfolioDeleting} onDelete={s.handleDeletePortfolio}
      />

      <RebalancePreviewModal
        opened={s.rebalance.previewOpened} onClose={() => s.rebalance.setPreviewOpened(false)}
        baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'}
        rebalanceMode={s.rebalance.mode} onRebalanceModeChange={s.rebalance.setMode}
        rebalanceMaxTransactions={s.rebalance.maxTransactions} onRebalanceMaxTransactionsChange={s.rebalance.setMaxTransactions}
        rebalanceMinOrderValue={s.rebalance.minOrderValue} onRebalanceMinOrderValueChange={s.rebalance.setMinOrderValue}
        rebalanceCashToAllocate={s.rebalance.cashToAllocate} onRebalanceCashToAllocateChange={s.rebalance.setCashToAllocate}
        rebalanceTradeAt={s.rebalance.tradeAt} onRebalanceTradeAtChange={s.rebalance.setTradeAt}
        rebalanceRounding={s.rebalance.rounding} onRebalanceRoundingChange={s.rebalance.setRounding}
        rebalancePreviewError={s.rebalance.previewError} rebalancePreviewData={s.rebalance.previewData}
        rebalancePreviewLoading={s.rebalance.previewLoading} rebalanceCommitResult={s.rebalance.commitResult}
        rebalanceCommitLoading={s.rebalance.commitLoading}
        rebalanceSelectedRows={s.rebalance.selectedRows} onRebalanceSelectedRowsChange={s.rebalance.setSelectedRows}
        onLoadPreview={() => void s.rebalance.handleLoadPreview()} onCommitPreview={() => void s.rebalance.handleCommitPreview()}
      />

      <TargetAllocationDrawer
        opened={s.drawerOpened}
        onClose={() => s.setDrawerOpened(false)}
        portfolioId={portfolioId}
        onSaved={() => {
          s.setFormSuccess('Peso salvato. Caricamento storico prezzi in corso...');
          if (portfolioId) void s.loadTargetAllocation(portfolioId);
        }}
      />

      <TransactionDrawer
        opened={s.transactionDrawerOpened}
        onClose={() => s.setTransactionDrawerOpened(false)}
        portfolioId={portfolioId}
        selectedPortfolio={s.selectedPortfolio}
        onTransactionCreated={() => {
          s.setFormSuccess('Transazione salvata. Caricamento storico prezzi in corso...');
          if (portfolioId) void s.loadTransactions(portfolioId);
        }}
      />

      <EditTransactionModal
        opened={s.editTransactionOpened} onClose={() => s.setEditTransactionOpened(false)}
        label={s.editTransactionLabel} error={s.editTransactionError}
        tradeAt={s.editTradeAt} onTradeAtChange={s.setEditTradeAt}
        quantity={s.editQuantity} onQuantityChange={s.setEditQuantity}
        price={s.editPrice} onPriceChange={s.setEditPrice}
        fees={s.editFees} onFeesChange={s.setEditFees}
        taxes={s.editTaxes} onTaxesChange={s.setEditTaxes}
        notes={s.editNotes} onNotesChange={s.setEditNotes}
        saving={s.editTransactionSaving} onSave={s.handleUpdateTransaction}
      />

      <DeleteTransactionModal
        opened={s.transactionDeleteOpened} onClose={() => s.setTransactionDeleteOpened(false)}
        label={s.transactionLabelToDelete} deleting={s.deletingTransactionId != null}
        deletingId={s.deletingTransactionId} transactionId={s.transactionIdToDelete}
        onConfirm={() => void s.confirmDeleteTransaction()}
      />

      <CsvImportModal
        opened={s.csvImportOpened} onClose={() => s.setCsvImportOpened(false)}
        portfolioId={portfolioId}
        onPortfolioCreated={(id) => { void s.loadPortfolios(String(id)); }}
        onImportComplete={(id) => { void s.loadPortfolios(String(id)); void s.loadTransactions(id); }}
      />

      {ENABLE_TARGET_ALLOCATION && s.selectedPortfolioId && (
        <TargetAllocationCsvImportModal
          opened={s.targetCsvImportOpened} onClose={() => s.setTargetCsvImportOpened(false)}
          portfolioId={Number(s.selectedPortfolioId)}
          onImportComplete={() => { if (s.selectedPortfolioId) void s.loadTargetAllocation(Number(s.selectedPortfolioId)); }}
        />
      )}

      {s.selectedPortfolioId && (
        <PacRuleDrawer
          opened={s.pacDrawerOpened}
          onClose={() => { s.setPacDrawerOpened(false); s.setEditingPacRule(null); }}
          portfolioId={Number(s.selectedPortfolioId)}
          baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'}
          editingRule={s.editingPacRule}
          selectedAssetId={null}
          selectedAssetSymbol={null}
          onSaved={() => s.setPacRefreshTrigger((n) => n + 1)}
        />
      )}

      {s.copilotAvailable && (
        <ActionIcon
          variant="filled" color="teal" size={52} radius="xl"
          onClick={s.openCopilot} aria-label="Apri Portfolio Copilot"
          style={{ position: 'fixed', bottom: s.isMobile ? 80 : 24, right: 24, zIndex: 100, boxShadow: '0 4px 16px rgba(0,0,0,0.2)' }}
        >
          <IconRobot size={24} />
        </ActionIcon>
      )}

      <CopilotChat opened={s.copilotOpened} onClose={s.closeCopilot} portfolioId={portfolioId} />

      {assetInfoModal && (
        <AssetInfoModal
          assetId={assetInfoModal.assetId}
          symbol={assetInfoModal.symbol}
          opened={!!assetInfoModal}
          onClose={() => setAssetInfoModal(null)}
        />
      )}
    </>
  );
}
