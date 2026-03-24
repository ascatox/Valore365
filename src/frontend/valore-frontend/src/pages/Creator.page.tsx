import { useState } from 'react';
import { Button, Group, Stack, Stepper, Notification } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { CreatorMethodPicker } from '../components/creator/CreatorMethodPicker';
import { CreatorModelLibrary } from '../components/creator/CreatorModelLibrary';
import { CreatorProfileQuiz } from '../components/creator/CreatorProfileQuiz';
import { CreatorCustomize } from '../components/creator/CreatorCustomize';
import { CreatorCapital } from '../components/creator/CreatorCapital';
import { CreatorConfirm } from '../components/creator/CreatorConfirm';
import {
  createPortfolio,
  upsertPortfolioTargetAllocation,
  ensureAsset,
  getAssetLatestQuote,
  createTransaction,
} from '../services/api';
import type { AllocationSlot, CreatorMethod, PortfolioModel } from '../components/creator/types';

const STEP_LABELS = ['Scegli', 'Seleziona', 'Personalizza', 'Capitale', 'Conferma'];

export function CreatorPage() {
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 48em)');

  const [active, setActive] = useState(0);
  const [method, setMethod] = useState<CreatorMethod | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [slots, setSlots] = useState<AllocationSlot[]>([]);
  const [portfolioName, setPortfolioName] = useState('');
  const [capital, setCapital] = useState<number | ''>('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ---- Step 1 ---- */
  const handleMethodPick = (m: CreatorMethod) => {
    setMethod(m);
    setSelectedModelId(null);
    setSlots([]);
    setPortfolioName('');
    setCapital('');
    setError(null);
    if (m === 'model' || m === 'profile') {
      setActive(1);
    }
    // manual verra' gestito nelle prossime iterazioni
  };

  /* ---- Step 2: modello selezionato ---- */
  const handleModelSelect = (model: PortfolioModel) => {
    setSelectedModelId(model.id);
    setSlots([...model.slots]);
    setPortfolioName(model.name);
  };

  /* ---- Step finale: crea portafoglio con transazioni ---- */
  const handleConfirm = async () => {
    const numericCapital = typeof capital === 'number' ? capital : 0;
    if (!portfolioName.trim() || creating || numericCapital <= 0) return;
    setCreating(true);
    setError(null);

    try {
      const portfolio = await createPortfolio({
        name: portfolioName.trim(),
        base_currency: 'EUR',
        timezone: 'Europe/Rome',
      });

      const now = new Date().toISOString();

      for (const slot of slots) {
        if (!slot.ticker) continue;

        // 1. Ensure asset exists (pass ISIN for justETF enrichment)
        const ensured = await ensureAsset({
          source: 'provider',
          symbol: slot.ticker,
          name: slot.label,
          portfolio_id: portfolio.id,
          isin: slot.isin ?? null,
        });

        // 2. Set target allocation
        await upsertPortfolioTargetAllocation(portfolio.id, {
          asset_id: ensured.asset_id,
          weight_pct: slot.weight,
        });

        // 3. Get current price and create buy transaction
        const quote = await getAssetLatestQuote(ensured.asset_id);
        if (quote.price > 0) {
          const amountForSlot = (numericCapital * slot.weight) / 100;
          const quantity = Math.floor((amountForSlot / quote.price) * 10000) / 10000; // 4 decimali
          if (quantity > 0) {
            await createTransaction({
              portfolio_id: portfolio.id,
              asset_id: ensured.asset_id,
              side: 'buy',
              trade_at: now,
              quantity,
              price: quote.price,
              fees: 0,
              taxes: 0,
              trade_currency: 'EUR',
              notes: `Acquisto iniziale da Creator — modello ${portfolioName}`,
            });
          }
        }
      }

      window.dispatchEvent(
        new CustomEvent('valore365:portfolios-changed', { detail: { count: 1 } }),
      );
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore durante la creazione del portafoglio');
    } finally {
      setCreating(false);
    }
  };

  /* ---- Navigazione stepper ---- */
  const canGoNext = () => {
    if (active === 1 && !selectedModelId) return false;
    if (active === 2) {
      const total = slots.reduce((s, sl) => s + sl.weight, 0);
      if (Math.abs(total - 100) >= 0.5) return false;
    }
    if (active === 3 && (typeof capital !== 'number' || capital <= 0)) return false;
    return true;
  };

  const next = () => {
    if (canGoNext() && active < STEP_LABELS.length - 1) {
      setActive((a) => a + 1);
    }
  };

  const back = () => {
    if (active === 1 && method) {
      setActive(0);
      setMethod(null);
      setSelectedModelId(null);
    } else if (active > 0) {
      setActive((a) => a - 1);
    }
  };

  return (
    <PageLayout>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Creator"
          title="Crea il tuo portafoglio"
          description="Scegli un modello, personalizzalo e inizia a monitorare."
        />

        <Stepper
          active={active}
          size={isMobile ? 'xs' : 'sm'}
          orientation={isMobile ? 'horizontal' : 'horizontal'}
        >
          {STEP_LABELS.map((label) => (
            <Stepper.Step key={label} label={isMobile ? undefined : label} />
          ))}
        </Stepper>

        {/* Step 0: scelta metodo */}
        {active === 0 && <CreatorMethodPicker onPick={handleMethodPick} />}

        {/* Step 1: libreria modelli */}
        {active === 1 && method === 'model' && (
          <CreatorModelLibrary
            selected={selectedModelId}
            onSelect={handleModelSelect}
          />
        )}

        {active === 1 && method === 'profile' && (
          <CreatorProfileQuiz
            selectedModelId={selectedModelId}
            onSelectModel={handleModelSelect}
          />
        )}

        {/* Step 2: personalizza */}
        {active === 2 && (
          <CreatorCustomize slots={slots} onChange={setSlots} />
        )}

        {/* Step 3: capitale iniziale */}
        {active === 3 && (
          <CreatorCapital capital={capital} onChange={setCapital} slots={slots} />
        )}

        {/* Step 4: conferma */}
        {active === 4 && (
          <CreatorConfirm
            slots={slots}
            portfolioName={portfolioName}
            onNameChange={setPortfolioName}
            onConfirm={handleConfirm}
            loading={creating}
            capital={typeof capital === 'number' ? capital : 0}
          />
        )}

        {error && (
          <Notification color="red" onClose={() => setError(null)}>
            {error}
          </Notification>
        )}

        {/* Navigazione */}
        {active > 0 && (
          <Group justify="space-between">
            <Button variant="default" onClick={back}>
              Indietro
            </Button>
            {active < STEP_LABELS.length - 1 && (
              <Button onClick={next} disabled={!canGoNext()}>
                Avanti
              </Button>
            )}
          </Group>
        )}
      </Stack>
    </PageLayout>
  );
}
