import { Button, Group, Menu, Stack, Text } from '@mantine/core';
import { IconAdjustments, IconChevronDown, IconFlask, IconRobot } from '@tabler/icons-react';
import type {
  TribunalCaseFile,
  TribunalContestedPoint,
  TribunalFact,
  TribunalVoiceInfo,
} from '../../../services/api/tribunalTypes';
import { maskMoneyInText, splitTemplate, voiceName } from './tribunalFormat';

// Dalle divergenze all'azione (TASK-70, ui-spec §9): per un punto conteso porta l'utente ai suoi
// strumenti (Copilot per capire, I miei parametri con una regola senza soglie da confermare,
// Laboratorio per simulare). Non salva nulla, non propone strumenti, importi o soglie.

export interface TribunalContestedActionsProps {
  point: TribunalContestedPoint;
  caseFile: TribunalCaseFile;
  voices: TribunalVoiceInfo[];
  isAggregate: boolean;
  privacy: boolean;
  copilotAvailable: boolean;
  parametriEnabled: boolean;
  labEnabled: boolean;
  /** Doctor.page: handleAskCopilot (apre la chat con la domanda precompilata). */
  onAskCopilot: (text: string) => void;
  /** Apre «I miei parametri» con una nuova regola, senza soglie, sulla metrica scelta. */
  onOpenPolicyDraft: (metricCode: string) => void;
  /** Apre il Laboratorio senza precompilare operazioni o pesi. */
  onOpenLab: () => void;
}

/** Testo usato nel prompt per un fatto sensibile in Privacy Mode (mai il valore). */
const HIDDEN_VALUE = '[dato nascosto]';

const oneLine = (text: string) => text.replace(/\s+/g, ' ').trim();

function factMap(caseFile: TribunalCaseFile): Map<string, TribunalFact> {
  return new Map(caseFile.facts.map((fact) => [fact.id, fact]));
}

/** Testo da `text_template` con i valori dei fatti; i sensibili sono nascosti in Privacy Mode. */
function templateText(template: string, fallback: string, facts: Map<string, TribunalFact>, privacy: boolean): string {
  const parts = splitTemplate(template);
  if (parts.length === 0) return oneLine(maskMoneyInText(fallback, privacy));
  let out = '';
  for (const part of parts) {
    if (part.kind === 'text') {
      out += maskMoneyInText(part.value, privacy);
      continue;
    }
    const fact = facts.get(part.id);
    // Segnaposto senza fatto (non dovrebbe accadere): testo finale, come TribunalRichText.
    if (!fact) return oneLine(maskMoneyInText(fallback, privacy));
    out += privacy && fact.sensitive ? HIDDEN_VALUE : fact.formatted;
  }
  return oneLine(out);
}

/** Fatti citati dal punto e poi dai lati, senza duplicati, nell'ordine di apparizione. */
export function contestedFactIds(point: TribunalContestedPoint): string[] {
  const ids = [...point.fact_ids, ...point.sides.flatMap((side) => side.fact_ids)];
  return [...new Set(ids)];
}

/**
 * Domanda precompilata per il Copilot (ui-spec §9): punto, dati citati, i due lati, richiesta di
 * capire. Nessuno strumento da comprare o vendere, nessuna soglia.
 */
export function buildContestedCopilotPrompt(
  point: TribunalContestedPoint,
  caseFile: TribunalCaseFile,
  voices: TribunalVoiceInfo[],
  options: { privacy?: boolean } = {},
): string {
  const privacy = options.privacy ?? false;
  const facts = factMap(caseFile);
  const cited = contestedFactIds(point)
    .map((id) => facts.get(id))
    .filter((fact): fact is TribunalFact => fact != null && !(privacy && fact.sensitive))
    .map((fact) => `${oneLine(maskMoneyInText(fact.label, privacy))}: ${fact.formatted}`);

  const lines = [
    `Nel Tribunale del portafoglio le voci non concordano su questo punto: «${templateText(point.text_template, point.text, facts, privacy)}».`,
  ];
  if (cited.length > 0) lines.push(`Dati citati: ${cited.join('; ')}.`);
  for (const side of point.sides) {
    const names = side.voices.map((id) => voiceName(id, voices)).join(', ');
    lines.push(`${names}: «${templateText(side.summary_template, side.summary, facts, privacy)}»`);
  }
  lines.push('Aiutami a capire cosa misurano questi dati e quali domande pormi. Nessuna indicazione di acquisto o vendita.');
  return lines.join('\n');
}

/** Etichetta di una metrica: quella del fatto `metric.<code>` del fascicolo, altrimenti il codice. */
export function metricLabelFromCaseFile(code: string, caseFile: TribunalCaseFile): string {
  return caseFile.facts.find((fact) => fact.key === `metric.${code}`)?.label ?? code;
}

export function TribunalContestedActions({
  point, caseFile, voices, isAggregate, privacy, copilotAvailable, parametriEnabled, labEnabled,
  onAskCopilot, onOpenPolicyDraft, onOpenLab,
}: TribunalContestedActionsProps) {
  const metricCodes = [...new Set(point.metric_codes ?? [])];
  const showCopilot = copilotAvailable;
  const showParametri = parametriEnabled && metricCodes.length > 0;
  const showLab = labEnabled;
  if (!showCopilot && !showParametri && !showLab) return null;

  const parametriLabel = 'Fissa un tuo parametro';

  return (
    <Stack gap={4} data-testid="tribunal-contested-actions" data-point-id={point.id}>
      <Group gap="xs" wrap="wrap" role="group" aria-label="Azioni sul punto conteso">
        {showCopilot && (
          <Button
            variant="light"
            size="xs"
            leftSection={<IconRobot size={14} aria-hidden="true" />}
            onClick={() => onAskCopilot(buildContestedCopilotPrompt(point, caseFile, voices, { privacy }))}
            data-action="copilot"
          >
            Approfondisci con il Copilot
          </Button>
        )}
        {showParametri && metricCodes.length === 1 && (
          <Button
            variant="light"
            size="xs"
            leftSection={<IconAdjustments size={14} aria-hidden="true" />}
            onClick={() => onOpenPolicyDraft(metricCodes[0])}
            data-action="parametri"
          >
            {parametriLabel}
          </Button>
        )}
        {showParametri && metricCodes.length > 1 && (
          <Menu position="bottom-start" withinPortal shadow="md">
            <Menu.Target>
              <Button
                variant="light"
                size="xs"
                leftSection={<IconAdjustments size={14} aria-hidden="true" />}
                rightSection={<IconChevronDown size={14} aria-hidden="true" />}
                data-action="parametri"
              >
                {parametriLabel}
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Label>Su quale metrica?</Menu.Label>
              {metricCodes.map((code) => (
                <Menu.Item key={code} onClick={() => onOpenPolicyDraft(code)} data-metric-code={code}>
                  {metricLabelFromCaseFile(code, caseFile)}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        )}
        {showLab && (
          <Button
            variant="light"
            size="xs"
            leftSection={<IconFlask size={14} aria-hidden="true" />}
            onClick={() => onOpenLab()}
            data-action="laboratorio"
          >
            Prova uno scenario
          </Button>
        )}
      </Group>
      {isAggregate && (showParametri || showLab) && (
        <Text size="xs" c="dimmed" data-testid="tribunal-actions-aggregate-note">
          Parametri e scenari valgono per l&apos;insieme dei portafogli selezionati.
        </Text>
      )}
    </Stack>
  );
}
