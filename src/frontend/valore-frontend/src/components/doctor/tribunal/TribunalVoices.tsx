import { useMemo } from 'react';
import { Group, Loader, SimpleGrid, Stack, Tabs, Text } from '@mantine/core';
import type { TribunalRebuttal, TribunalVoiceId } from '../../../services/api/tribunalTypes';
import type { TribunalSessionState } from './useTribunalSession';
import { TribunalVoiceColumn, VoiceDot, type TribunalVoiceView } from './TribunalVoiceColumn';
import { resolveVoices, voiceMeta, voiceOfElementId } from './tribunalFormat';

type VoiceSource = Pick<TribunalSessionState,
  'status' | 'voices' | 'argumentsByVoice' | 'rebuttals' | 'voiceErrors' | 'completedPhases' | 'discarded'>;

/** Dati per colonna, nell'ordine canonico fisso (mai riordinate, ui-spec §2.1, §7). */
export function buildVoiceViews(state: VoiceSource): TribunalVoiceView[] {
  const openingClosed = state.completedPhases.includes('apertura');
  return resolveVoices(state.voices).map((info) => {
    const args = state.argumentsByVoice[info.id] ?? [];
    const errors = state.voiceErrors.filter((error) => error.voice === info.id);
    const hasOpeningError = errors.some((error) => error.phase === 'apertura');
    const closed = openingClosed || (state.discarded.byVoice[info.id] ?? 0) > 0;
    return {
      info,
      arguments: args,
      given: state.rebuttals.filter((rebuttal) => rebuttal.voice === info.id),
      errors,
      pending: state.status === 'running' && args.length === 0 && !hasOpeningError && !closed,
      noneAdmitted: args.length === 0 && !hasOpeningError && closed,
    };
  });
}

/** Colonna/scheda in cui compare una card: un argomento sta nella sua voce, una replica sotto il bersaglio. */
export function voiceOfCard(elementId: string, rebuttals: TribunalRebuttal[]): TribunalVoiceId | null {
  const rebuttal = rebuttals.find((item) => item.id === elementId);
  if (rebuttal) return rebuttal.target_voice;
  return elementId.startsWith('A-') ? voiceOfElementId(elementId) : null;
}

interface TribunalVoicesProps {
  views: TribunalVoiceView[];
  rebuttals: TribunalRebuttal[];
  /** < 62em: schede invece di colonne. */
  compact: boolean;
  activeVoice: TribunalVoiceId;
  onActiveVoiceChange: (voice: TribunalVoiceId) => void;
}

/** Le tre voci: colonne di uguale larghezza su desktop, schede su tablet e mobile (ui-spec §2). */
export function TribunalVoices({ views, rebuttals, compact, activeVoice, onActiveVoiceChange }: TribunalVoicesProps) {
  const rebuttalsByTarget = useMemo(() => {
    const map = new Map<string, TribunalRebuttal[]>();
    rebuttals.forEach((rebuttal) => {
      map.set(rebuttal.target_argument_id, [...(map.get(rebuttal.target_argument_id) ?? []), rebuttal]);
    });
    return map;
  }, [rebuttals]);

  if (!compact) {
    return (
      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg" data-testid="tribunal-voices" data-layout="columns">
        {views.map((view) => (
          <TribunalVoiceColumn key={view.info.id} view={view} rebuttalsByTarget={rebuttalsByTarget} />
        ))}
      </SimpleGrid>
    );
  }

  return (
    <Tabs
      value={activeVoice}
      onChange={(value) => value && onActiveVoiceChange(value as TribunalVoiceId)}
      data-testid="tribunal-voices"
      data-layout="tabs"
      keepMounted
      styles={{
        list: { flexWrap: 'nowrap' },
        tab: { minWidth: 0, paddingInline: 2, paddingBlock: 8, height: 'auto', fontSize: 'var(--mantine-font-size-sm)' },
        tabLabel: { minWidth: 0 },
      }}
    >
      <Tabs.List grow>
        {views.map((view) => (
          <Tabs.Tab key={view.info.id} value={view.info.id}>
            <Stack gap={2} align="center">
              <Text span inherit fw={500} style={{ whiteSpace: 'nowrap' }}>{voiceMeta(view.info.id).tabLabel}</Text>
              <Group gap={6} wrap="nowrap" justify="center" h={16}>
                <VoiceDot voice={view.info.id} />
                {view.pending
                  ? <Loader size={10} aria-label="In attesa" />
                  : <Text span size="xs" c="dimmed" aria-label={`${view.arguments.length} argomenti`}>{view.arguments.length}</Text>}
              </Group>
            </Stack>
          </Tabs.Tab>
        ))}
      </Tabs.List>
      {views.map((view) => (
        <Tabs.Panel key={view.info.id} value={view.info.id} pt="md">
          <TribunalVoiceColumn view={view} rebuttalsByTarget={rebuttalsByTarget} />
        </Tabs.Panel>
      ))}
    </Tabs>
  );
}
