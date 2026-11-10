import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Card, Group, Skeleton, Stack, Text, Title, VisuallyHidden } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconAlertTriangle, IconPlayerStop, IconRefresh, IconScale } from '@tabler/icons-react';
import { ApiRequestError } from '../../../services/api/client';
import type {
  TribunalCaseFile,
  TribunalContestedPoint,
  TribunalFact,
  TribunalVoiceId,
  TribunalVoiceInfo,
} from '../../../services/api/tribunalTypes';
import { TribunalCaseFilePanel } from './TribunalCaseFilePanel';
import { TribunalDisclaimer } from './TribunalDisclaimer';
import { TribunalDiscardedNotice } from './TribunalDiscardedNotice';
import { TribunalPhaseIndicator } from './TribunalPhaseIndicator';
import { TribunalStateCard } from './TribunalStateCard';
import { TribunalSynthesis } from './TribunalSynthesis';
import { TribunalVoices, buildVoiceViews, voiceOfCard } from './TribunalVoices';
import { TribunalViewContext, type TribunalViewContextValue } from './tribunalContext';
import { elementDomId, formatSessionDate, resolveVoices, tribunalMessage } from './tribunalFormat';
import {
  sessionToState,
  useTribunalFeature,
  useTribunalLatest,
  useTribunalSession,
  useTribunalStatus,
  type TribunalSessionState,
} from './useTribunalSession';

export interface TribunalSectionProps {
  portfolioIds: number[];
  isAggregate: boolean;
  privacy: boolean;
  /** Slot per le azioni di un punto conteso (TASK-70); assente = nessuna azione. */
  renderContestedActions?: (point: TribunalContestedPoint,
    context: { caseFile: TribunalCaseFile; voices: TribunalVoiceInfo[] }) => ReactNode;
}

/** `data-state` della sezione (ui-spec §4); `disabled` = feature spenta, sezione non mostrata. */
export type TribunalSectionState =
  | 'loading' | 'unavailable' | 'ready' | 'running' | 'completed' | 'error' | 'limit_reached' | 'aborted' | 'disabled';

/** < 62em (Mantine `md`): schede invece di colonne, dettagli in bottom sheet (ui-spec §2.2). */
export const TRIBUNAL_COMPACT_QUERY = '(max-width: 61.99em)';

const UNAVAILABLE_REASONS = new Set(['copilot_not_configured', 'provider_not_supported']);

const hasContent = (state: TribunalSessionState) => state.sessionId !== null || state.caseFile !== null;

function isFeatureDisabled(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === 'feature_disabled';
}

function liveAnnouncement(state: TribunalSectionState, session: TribunalSessionState): string {
  if (state === 'running') {
    if (session.synthesis) return 'Sintesi pronta';
    if (session.phase === 'sintesi') return 'Sintesi in corso';
    if (session.phase === 'replica') return 'Replica in corso';
    if (session.phase === 'apertura') return 'Apertura in corso';
    return 'Preparazione del fascicolo in corso';
  }
  if (state === 'completed') return 'Seduta conclusa';
  if (state === 'aborted') return 'Seduta interrotta';
  if (state === 'error') return 'Seduta interrotta da un errore';
  return '';
}

/**
 * «Tribunale del portafoglio»: tre voci AI discutono il portafoglio citando solo i fatti del
 * Doctor. Contenitore della sezione (ui-spec §3, §4): legge stato e ultima seduta, avvia la seduta
 * solo su richiesta esplicita e mostra avvertenza, voci, sintesi, scartati e fascicolo.
 */
export function TribunalSection({ portfolioIds, isAggregate, privacy, renderContestedActions }: TribunalSectionProps) {
  const compact = useMediaQuery(TRIBUNAL_COMPACT_QUERY, false, { getInitialValueInEffect: false }) === true;
  const navigate = useNavigate();
  const titleId = useId();

  const feature = useTribunalFeature();
  const statusQuery = useTribunalStatus(portfolioIds, feature.enabled);
  const latestQuery = useTribunalLatest(portfolioIds, feature.enabled);
  const session = useTribunalSession(portfolioIds);

  const status = statusQuery.data ?? null;
  const latest = latestQuery.data ?? null;
  const savedSession = latest?.session ?? null;
  const savedState = useMemo(() => (savedSession ? sessionToState(savedSession) : null), [savedSession]);

  // ---- macchina degli stati (§4)
  let state: TribunalSectionState;
  if (feature.isLoading) state = 'loading';
  else if (!feature.enabled || isFeatureDisabled(statusQuery.error)) state = 'disabled';
  else if (session.status !== 'idle') state = session.status;
  else if (statusQuery.isLoading || latestQuery.isLoading) state = 'loading';
  else if (statusQuery.isError || !status) state = 'error';
  else if (!status.available && status.reason && UNAVAILABLE_REASONS.has(status.reason)) state = 'unavailable';
  else if (!status.available && status.reason === 'daily_limit_reached') state = 'limit_reached';
  else if (savedState) state = 'completed';
  else if (!status.available) state = 'unavailable';
  else state = 'ready';

  // ---- contenuto mostrato: la seduta in corso/arrivata, oppure quella salvata in sola lettura
  const liveShown = session.status !== 'idle' && (session.status === 'running' || hasContent(session));
  const shown: TribunalSessionState | null = liveShown ? session : savedState;
  const showingSaved = !liveShown && shown !== null;
  const readOnly = showingSaved && state !== 'completed';
  const source: 'saved' | 'live' | undefined = state === 'completed' ? (showingSaved ? 'saved' : 'live') : undefined;

  const voices = useMemo(() => resolveVoices(shown?.voices), [shown?.voices]);
  const facts = useMemo(() => {
    const map = new Map<string, TribunalFact>();
    shown?.caseFile?.facts.forEach((fact) => map.set(fact.id, fact));
    return map;
  }, [shown?.caseFile]);
  const views = useMemo(() => (shown ? buildVoiceViews(shown) : []), [shown]);

  // ---- navigazione verso una card (scroll e focus; su mobile cambia scheda)
  const [activeVoice, setActiveVoice] = useState<TribunalVoiceId>('indicizzatore');
  const [focusTarget, setFocusTarget] = useState<{ id: string; nonce: number } | null>(null);
  const rebuttals = shown?.rebuttals;
  const goTo = useCallback((elementId: string) => {
    const voice = voiceOfCard(elementId, rebuttals ?? []);
    if (compact && voice) setActiveVoice(voice);
    setFocusTarget({ id: elementId, nonce: Date.now() });
  }, [compact, rebuttals]);

  useEffect(() => {
    if (!focusTarget) return;
    const element = document.getElementById(elementDomId(focusTarget.id));
    if (!element) return;
    element.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    element.focus({ preventScroll: true });
  }, [focusTarget, activeVoice]);

  const context = useMemo<TribunalViewContextValue>(
    () => ({ facts, voices, privacy, compact, goTo }),
    [facts, voices, privacy, compact, goTo],
  );

  const caseFile = shown?.caseFile ?? null;
  const contestedActions = useMemo(() => {
    if (!renderContestedActions || !caseFile || readOnly) return undefined;
    return (point: TribunalContestedPoint) => renderContestedActions(point, { caseFile, voices });
  }, [renderContestedActions, caseFile, voices, readOnly]);

  const root = {
    'data-state': state,
    'data-phase': state === 'running' ? (session.phase ?? undefined) : undefined,
    'data-source': source,
  };

  if (state === 'disabled') return <Box {...root} hidden data-testid="tribunal-section" />;

  if (state === 'loading') {
    return (
      <Stack gap="md" {...root} data-testid="tribunal-section" aria-busy="true">
        <TribunalDisclaimer compact={compact} />
        <Skeleton height={88} radius="lg" />
        <Skeleton height={220} radius="lg" />
      </Stack>
    );
  }

  // ---- messaggi e azioni
  const keyFromServer = status?.key_source === 'server';
  const sessionError = session.status === 'error' || session.status === 'limit_reached' ? session.error : null;
  const resetsAt = session.error?.resetsAt ?? status?.limit?.resets_at ?? null;
  let message: string | null = null;
  if (state === 'unavailable') message = tribunalMessage(status?.reason, status?.message, { privacy });
  if (state === 'limit_reached') message = tribunalMessage('daily_limit_reached', null, { resetsAt });
  if (state === 'error') {
    if (sessionError) {
      message = tribunalMessage(sessionError.code, sessionError.message, { privacy, resetsAt });
    } else {
      const failure = statusQuery.error;
      const code = failure instanceof ApiRequestError ? failure.code : 'network_error';
      message = tribunalMessage(code ?? 'internal_error', failure instanceof ApiRequestError ? failure.message : null, { privacy });
    }
  }
  const onRetry = state === 'error'
    ? (sessionError ? (sessionError.retryable ? session.start : null) : () => { void statusQuery.refetch(); })
    : null;

  const sessionDate = shown && (showingSaved || shown.reused) ? formatSessionDate(shown.createdAt) : null;
  const dataChanged = showingSaved && latest?.data_changed === true;
  const showPhases = shown !== null && (state === 'running' || hasContent(shown));
  const scopeLabel = isAggregate
    ? `Vista aggregata di ${new Set(portfolioIds).size} portafogli`
    : 'Portafoglio selezionato';

  const stateCard = (() => {
    switch (state) {
      case 'ready':
        return <TribunalStateCard kind="ready" status={status} voices={voices} compact={compact} onStart={session.start} />;
      case 'aborted':
        return <TribunalStateCard kind="aborted" voices={voices} compact={compact} onStart={session.start} />;
      case 'unavailable':
        return (
          <TribunalStateCard kind="unavailable" message={message} voices={voices} compact={compact} onOpenSettings={() => navigate('/settings')} />
        );
      case 'limit_reached':
        return <TribunalStateCard kind="limit_reached" message={message} voices={voices} compact={compact} />;
      case 'error':
        return (
          <TribunalStateCard
            kind="error"
            message={message}
            voices={voices}
            compact={compact}
            incomplete={liveShown}
            onRetry={onRetry}
          />
        );
      default:
        return null;
    }
  })();

  return (
    <TribunalViewContext.Provider value={context}>
      <Stack
        component="section"
        gap="md"
        aria-labelledby={titleId}
        data-testid="tribunal-section"
        {...root}
        style={{ minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}
      >
        <TribunalDisclaimer compact={compact} />
        <VisuallyHidden role="status" aria-live="polite" data-testid="tribunal-live">
          {liveAnnouncement(state, session)}
        </VisuallyHidden>

        <Card withBorder radius="lg" padding={compact ? 'md' : 'lg'}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start" gap="sm" wrap="wrap">
              <Stack gap={2} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="nowrap">
                  <IconScale size={22} aria-hidden="true" style={{ flexShrink: 0 }} />
                  <Title order={3} id={titleId}>Tribunale del portafoglio</Title>
                </Group>
                <Text size="sm" c="dimmed" data-testid="tribunal-scope">
                  {scopeLabel}
                  {sessionDate ? ` · Seduta del ${sessionDate}` : ''}
                </Text>
              </Stack>
              {state === 'running' && (
                <Button
                  variant="default"
                  leftSection={<IconPlayerStop size={16} />}
                  onClick={session.stop}
                  fullWidth={compact}
                  data-testid="tribunal-stop"
                >
                  Interrompi
                </Button>
              )}
              {state === 'completed' && (
                <Stack gap={2} align={compact ? 'stretch' : 'flex-end'} style={compact ? { width: '100%' } : undefined}>
                  <Button
                    variant="light"
                    leftSection={<IconRefresh size={16} />}
                    onClick={session.redo}
                    fullWidth={compact}
                    data-testid="tribunal-redo"
                  >
                    Rifai la seduta
                  </Button>
                  {keyFromServer && <Text size="xs" c="dimmed" ta={compact ? 'center' : 'right'}>Usa una delle sedute di oggi</Text>}
                </Stack>
              )}
            </Group>
            {showPhases && shown && (
              <TribunalPhaseIndicator
                phase={shown.phase}
                hasCaseFile={shown.caseFile !== null}
                completed={shown.status === 'completed'}
                completedPhases={shown.completedPhases}
                compact={compact}
              />
            )}
            {dataChanged && (
              <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={16} />} data-testid="tribunal-data-changed">
                I dati del portafoglio sono cambiati da questa seduta: alcuni valori potrebbero non essere più attuali.
              </Alert>
            )}
          </Stack>
        </Card>

        {stateCard}

        {shown && (state === 'running' || hasContent(shown)) && (
          <Stack gap="lg" data-testid="tribunal-content" data-read-only={readOnly ? 'true' : undefined}>
            {readOnly && (
              <Text size="sm" c="dimmed">{`Ultima seduta salvata${sessionDate ? `, del ${sessionDate}` : ''} (sola lettura).`}</Text>
            )}
            <TribunalVoices
              views={views}
              rebuttals={shown.rebuttals}
              compact={compact}
              activeVoice={activeVoice}
              onActiveVoiceChange={setActiveVoice}
            />
            <TribunalSynthesis
              synthesis={shown.synthesis}
              pending={shown.status === 'running' && shown.phase === 'sintesi'}
              renderContestedActions={contestedActions}
            />
            <TribunalDiscardedNotice discarded={shown.discarded} />
            {shown.caseFile && <TribunalCaseFilePanel caseFile={shown.caseFile} />}
          </Stack>
        )}
      </Stack>
    </TribunalViewContext.Provider>
  );
}
