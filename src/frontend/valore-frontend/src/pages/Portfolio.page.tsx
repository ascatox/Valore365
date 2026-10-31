import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Table,
  Button,
  Text,
  Group,
  Alert,
  Loader,
  ActionIcon,
  Tabs,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import { IconEdit, IconPlus, IconTrash, IconArrowsExchange, IconFileImport, IconCoins, IconRobot, IconInfoCircle, IconStack2, IconWallet } from '@tabler/icons-react';
import { AggregateReadOnlyTooltip, AggregateScopeNotice, AggregateUnavailableNotice } from '../scope/AggregateReadOnly';
import { scopePortfolioIds } from '../scope/portfolioScope';
import { CashSection } from '../components/portfolio/sections/CashSection.tsx';
import { CsvImportModal } from '../components/portfolio/modals/CsvImportModal.tsx';
import { TargetAllocationCsvImportModal } from '../components/portfolio/modals/TargetAllocationCsvImportModal.tsx';
import { PacRuleDrawer } from '../components/portfolio/drawers/PacRuleDrawer.tsx';
import { PacSection } from '../components/portfolio/sections/PacSection.tsx';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher.tsx';
import { PortfolioAiExportMenu } from '../components/portfolio/PortfolioAiExportMenu.tsx';
import { usePortfolioAiExport } from '../components/portfolio/hooks/usePortfolioAiExport';

import { TransactionsSection } from '../components/portfolio/sections/TransactionsSection.tsx';

import { formatNum, formatMoneyOrNA, formatDateTime, formatTransactionSideLabel, getTransactionNetTotal, getTransactionSideColor } from '../components/dashboard/formatters';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { useSwipeTabs } from '../hooks/useSwipeTabs';

import { usePortfolioPage } from '../components/portfolio/hooks/usePortfolioPage';
import { usePortfolioSummary } from '../components/dashboard/hooks/queries';
import { RebalancePreviewModal } from '../components/portfolio/modals/RebalancePreviewModal';
import { PortfolioModal, PortfolioCloneModal, PortfolioDeleteModal, EditTransactionModal, DeleteTransactionModal } from '../components/portfolio/modals/PortfolioFormModals';
import { TransactionDrawer } from '../components/portfolio/drawers/TransactionDrawer';
import { TargetAllocationDrawer } from '../components/portfolio/drawers/TargetAllocationDrawer';
import { PortfolioEmptyState } from '../components/portfolio/sections/PortfolioEmptyState';
import { TransactionMobileList } from '../components/portfolio/TransactionMobileList';
import { AssetInfoModal } from '../components/dashboard/holdings/AssetInfoModal';

// Order of the view tabs, for swiping between them on mobile.
const PORTFOLIO_VIEWS = ['transactions', 'cash', 'pac'] as const;

export function PortfolioPage() {
  const s = usePortfolioPage();
  // Null in the aggregate view: everything below that writes needs it.
  const portfolioId = s.selectedPortfolioId ? Number(s.selectedPortfolioId) : null;
  const readOnly = s.isAggregate;
  const scopeIds = scopePortfolioIds(s.scope);
  const { data: summary } = usePortfolioSummary(s.scope);
  const [assetInfoModal, setAssetInfoModal] = useState<{ assetId: number; symbol: string } | null>(null);
  // Single portfolio or aggregate: the export is read-only, so it stays available.
  const aiExport = usePortfolioAiExport(s.scope);
  const swipeRef = useSwipeTabs({
    tabs: PORTFOLIO_VIEWS,
    active: s.portfolioView,
    onChange: (view) => s.setPortfolioView(view as (typeof PORTFOLIO_VIEWS)[number]),
    enabled: s.isMobile,
  });

  // Quick actions from the mobile "+" sheet arrive as ?azione=<name>.
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedAction = searchParams.get('azione');
  useEffect(() => {
    if (!requestedAction || s.loadingPortfolios) return;
    // Aggregate view: read-only, the write actions only open their tab.
    switch (requestedAction) {
      case 'nuova-transazione':
        s.setPortfolioView('transactions');
        if (s.selectedPortfolioId && !readOnly) s.setTransactionDrawerOpened(true);
        break;
      case 'importa':
        s.setPortfolioView('transactions');
        if (!readOnly) s.setCsvImportOpened(true);
        break;
      case 'nuova-regola-pac':
        s.setPortfolioView('pac');
        if (s.selectedPortfolioId && !readOnly) {
          s.setEditingPacRule(null);
          s.setPacDrawerOpened(true);
        }
        break;
      case 'nuovo-portafoglio':
        s.openCreatePortfolioModal();
        break;
      default:
        break;
    }
    setSearchParams((params) => {
      params.delete('azione');
      return params;
    }, { replace: true });
  }, [requestedAction, readOnly, s, setSearchParams]);

  // --- Transaction table rows ---
  const transactionRows = s.sortedTransactions.map((tx) => {
    const total = getTransactionNetTotal(tx);
    return (
      <Table.Tr key={tx.id}>
        <Table.Td>{formatDateTime(tx.trade_at)}</Table.Td>
        {readOnly && <Table.Td>{tx.portfolio_name ?? '—'}</Table.Td>}
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
            {readOnly ? (
              <AggregateReadOnlyTooltip active>
                <Group gap={6} justify="flex-end" wrap="nowrap" style={{ minWidth: 74 }}>
                  <ActionIcon color="teal" variant="light" disabled aria-label={`Modifica transazione ${tx.id}`}>
                    <IconEdit size={16} />
                  </ActionIcon>
                  <ActionIcon color="red" variant="light" disabled aria-label={`Elimina transazione ${tx.id}`}>
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </AggregateReadOnlyTooltip>
            ) : (
              <Group gap={6} justify="flex-end" wrap="nowrap" style={{ minWidth: 74 }}>
                <ActionIcon color="teal" variant="light" onClick={() => s.openEditTransactionModal(tx)} aria-label={`Modifica transazione ${tx.id}`}>
                  <IconEdit size={16} />
                </ActionIcon>
                <ActionIcon color="red" variant="light" onClick={() => s.openDeleteTransactionModal(tx)} loading={s.deletingTransactionId === tx.id} aria-label={`Elimina transazione ${tx.id}`}>
                  <IconTrash size={16} />
                </ActionIcon>
              </Group>
            )}
          </Table.Td>
        )}
      </Table.Tr>
    );
  });

  // --- Totals row ---
  if (s.sortedTransactions.length > 0) {
    transactionRows.push(
      <Table.Tr key="transactions-total" style={{ fontWeight: 700, borderTop: '2px solid var(--mantine-color-dark-4)' }}>
        <Table.Td><Text fw={700} size="sm">TOTALE</Text></Table.Td>
        {readOnly && <Table.Td />}
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

  }


  return (
    <>
      <PageLayout>
      <PageHeader
        eyebrow="Gestione movimenti, liquidita e target"
        title="Portfolio"
        description="Operazioni, allocazione e struttura del portafoglio in una vista operativa unica."
        actions={(
          <Group align="flex-start" gap="xs" wrap="nowrap" style={s.isMobile ? { minWidth: 0 } : undefined}>
            <PortfolioSwitcher
              portfolios={s.portfolios}
              value={s.selectedPortfolioId}
              selectedPortfolioCashBalance={summary?.cash_balance ?? null}
              onChange={(nextValue) => s.setSelectedPortfolioId(nextValue)}
              loading={s.loadingPortfolios}
              style={s.isMobile ? { minWidth: 0 } : { width: '100%', maxWidth: 360 }}
              allowAggregate
              scope={s.scope}
              onScopeChange={s.setScope}
              aggregateTotalValue={readOnly && summary ? summary.market_value + summary.cash_balance : null}
              onCreatePortfolio={s.openCreatePortfolioModal}
              onEditPortfolio={s.writablePortfolioId != null ? s.openEditPortfolioModal : null}
              onClonePortfolio={s.writablePortfolioId != null ? s.openClonePortfolioModal : null}
              onDeletePortfolio={s.writablePortfolioId != null ? () => s.setPortfolioDeleteOpened(true) : null}
              onCopyForAi={s.scope ? aiExport.copyForAi : null}
              onDownloadMarkdown={s.scope ? aiExport.downloadMarkdown : null}
            />
            {!s.isMobile && <PortfolioAiExportMenu scope={s.scope} exportState={aiExport} />}
          </Group>
        )}
      />

      <Group mb={s.isMobile ? 'xs' : 'md'} align="flex-end" gap="xs">
        {!s.isMobile && (s.loadingPortfolios || s.loadingData) && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>

      <AggregateScopeNotice />

      {readOnly && (
        <Alert color="blue" variant="light" mb="md" icon={<IconStack2 size={18} />} title="Vista aggregata in sola lettura">
          Transazioni di {scopeIds.length} portafogli, con la colonna Portafoglio. Per aggiungere o modificare movimenti, liquidità, PAC o il portafoglio stesso seleziona un solo portafoglio. Lo snapshot per AI (copia o .md) esporta la vista aggregata.
        </Alert>
      )}

      <Group mb={s.isMobile ? 'xs' : 'md'} justify="space-between" wrap="wrap" gap="xs">
        <Tabs
          value={s.portfolioView}
          onChange={(value) => {
            const next = (value as 'transactions' | 'target' | 'pac' | 'cash') ?? 'transactions';
            s.setPortfolioView(next);
          }}
          variant="default"
          style={s.isMobile ? { width: '100%' } : undefined}
        >
            <Tabs.List style={{ flexWrap: 'nowrap', overflowX: 'auto', overflowY: 'hidden', WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none', paddingBottom: 0, gap: 0 }}>
              <Tabs.Tab value="transactions" leftSection={<IconArrowsExchange size={16} />}>
                <Text span>Transazioni</Text>
              </Tabs.Tab>
              <Tabs.Tab value="cash" leftSection={<IconWallet size={16} />}>
                <Text span>Liquidità</Text>
              </Tabs.Tab>
              <Tabs.Tab value="pac" leftSection={<IconCoins size={16} />}>
                <Text span>Piano di Accumulo</Text>
              </Tabs.Tab>
            </Tabs.List>
        </Tabs>
        {s.portfolioView === 'transactions' && !s.isMobile && (
          <Group gap="xs">
            <AggregateReadOnlyTooltip active={readOnly}>
              <Button leftSection={<IconPlus size={16} />} onClick={() => s.setTransactionDrawerOpened(true)} disabled={!s.selectedPortfolioId || readOnly}>
                Nuova Transazione
              </Button>
            </AggregateReadOnlyTooltip>
            <AggregateReadOnlyTooltip active={readOnly}>
              <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => s.setCsvImportOpened(true)} disabled={readOnly}>
                Importa
              </Button>
            </AggregateReadOnlyTooltip>
          </Group>
        )}
        {s.portfolioView === 'pac' && !s.isMobile && (
          <AggregateReadOnlyTooltip active={readOnly}>
            <Button leftSection={<IconPlus size={16} />} onClick={() => { s.setEditingPacRule(null); s.setPacDrawerOpened(true); }} disabled={!s.selectedPortfolioId || readOnly}>
              Nuova regola PAC
            </Button>
          </AggregateReadOnlyTooltip>
        )}
      </Group>

      <div ref={swipeRef}>
      {s.error && <Alert color="red" mb="md">{s.error}</Alert>}
      {s.transactionsError && <Alert color="red" mb="md">{s.transactionsError}</Alert>}
      {s.formSuccess && <Alert color="teal" mb="md">{s.formSuccess}</Alert>}
      {aiExport.copied && (
        <Alert color="teal" mb="md">
          {readOnly
            ? "Snapshot della vista aggregata copiato negli appunti, pronto da incollare in un'altra AI."
            : "Snapshot del portafoglio copiato negli appunti, pronto da incollare in un'altra AI."}
        </Alert>
      )}
      {aiExport.error && <Alert color="red" mb="md">{aiExport.error}</Alert>}

      {!s.loadingPortfolios && s.portfolios.length === 0 && (
        <PortfolioEmptyState
          onCreatePortfolio={s.openCreatePortfolioModal}
          onImportFromFile={() => s.setCsvImportOpened(true)}
        />
      )}

      {s.portfolioView === 'transactions' && (
        <TransactionsSection
          loading={s.loadingPortfolios || s.loadingTransactions}
          filterQuery={s.transactionFilterQuery}
          onFilterQueryChange={s.setTransactionFilterQuery}
          filterSide={s.transactionFilterSide}
          onFilterSideChange={s.setTransactionFilterSide}
          sortKey={s.transactionSortKey}
          onSortKeyChange={(value) => s.setTransactionSortKey((value as 'trade_at' | 'symbol' | 'side' | 'value') ?? 'trade_at')}
          sortDir={s.transactionSortDir}
          onSortDirChange={(value) => s.setTransactionSortDir((value as 'asc' | 'desc') ?? 'desc')}
          rows={transactionRows}
          mobileCards={(
            <TransactionMobileList
              transactions={s.sortedTransactions}
              groupByDate={s.transactionSortKey === 'trade_at'}
              totalLabel={s.sortedTransactions.length === 0
                ? null
                : s.transactionTotals.mixedCurrencies
                  ? 'Valute miste'
                  : formatMoneyOrNA(s.transactionTotals.totalValue, s.transactionTotals.currency ?? s.selectedPortfolio?.base_currency)}
              deletingId={s.deletingTransactionId}
              onEdit={s.openEditTransactionModal}
              onDelete={s.openDeleteTransactionModal}
              readOnly={readOnly}
            />
          )}
          hasRows={s.sortedTransactions.length > 0}
          selectedPortfolioId={s.selectedPortfolioId ?? (readOnly ? 'aggregate' : null)}
          showActions={!s.isMobile}
          showPortfolioColumn={readOnly}
        />
      )}

      {readOnly && (s.portfolioView === 'cash' || s.portfolioView === 'pac') && (
        <AggregateUnavailableNotice
          description={s.portfolioView === 'cash'
            ? 'La liquidità e i suoi movimenti sono gestiti per singolo portafoglio. Seleziona un solo portafoglio per vederli e modificarli.'
            : 'Le regole PAC sono definite per singolo portafoglio. Seleziona un solo portafoglio per vederle e modificarle.'}
        />
      )}

      {s.portfolioView === 'cash' && s.selectedPortfolioId && !readOnly && (
        <CashSection selectedPortfolioId={s.selectedPortfolioId} baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'} />
      )}

      {s.portfolioView === 'pac' && s.selectedPortfolioId && !readOnly && (
        <PacSection
          selectedPortfolioId={s.selectedPortfolioId}
          baseCurrency={s.selectedPortfolio?.base_currency ?? 'EUR'}
          onOpenPacDrawer={() => { s.setEditingPacRule(null); s.setPacDrawerOpened(true); }}
          onEditPacRule={(rule) => { s.setEditingPacRule(rule); s.setPacDrawerOpened(true); }}
          refreshTrigger={s.pacRefreshTrigger}
        />
      )}
      </div>
      </PageLayout>

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

      {s.selectedPortfolioId && (
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
          style={{ position: 'fixed', bottom: s.isMobile ? 'calc(92px + var(--safe-area-bottom-floating))' : 24, right: 24, zIndex: 100, boxShadow: '0 4px 16px rgba(0,0,0,0.2)' }}
        >
          <IconRobot size={24} />
        </ActionIcon>
      )}

      <CopilotChat
        opened={s.copilotOpened}
        onClose={s.closeCopilot}
        portfolioId={scopeIds[0] ?? null}
        portfolioIds={readOnly ? scopeIds : undefined}
        pageContext="portfolio"
      />

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
