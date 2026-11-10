import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TribunalCaseFile, TribunalContestedPoint } from '../../../services/api/tribunalTypes';
import { tribunalSessionFixture } from './fixtures';
import {
  buildContestedCopilotPrompt,
  contestedFactIds,
  metricLabelFromCaseFile,
  TribunalContestedActions,
  type TribunalContestedActionsProps,
} from './TribunalContestedActions';

// TASK-70 (ui-spec §9): the three actions of a contested point, their visibility and the
// pre-filled Copilot question, on the contract fixture.

const session = tribunalSessionFixture;
const caseFile = session.case_file;
const voices = session.voices;
const [concentration, drawdown] = session.synthesis!.contested_points;

const EXPECTED_C1 = [
  'Nel Tribunale del portafoglio le voci non concordano su questo punto: «Quanto pesa la concentrazione su VWCE.DE, che vale 46,6% del portafoglio.».',
  'Dati citati: Peso massimo singola posizione: 46,6%; Peso prime tre posizioni: 78,2%; Numero di posizioni: 6.',
  "L'indicizzatore: «Per l'indicizzatore la diversificazione dipende troppo da pochi strumenti: le prime tre posizioni valgono 78,2%.»",
  'Il fattoriale: «Per il fattoriale è una concentrazione consapevole su un fondo già diversificato, con 6 posizioni in tutto.»',
  'Aiutami a capire cosa misurano questi dati e quali domande pormi. Nessuna indicazione di acquisto o vendita.',
].join('\n');

/** Words that would turn the question into an operation or a threshold (§9, contract §7.6). */
const PRESCRIPTIVE = /\b(compra|comprare|acquista|vendi|vendere|ribilancia|sostituisci|liquida|soglia|limite massimo|non superare)\b/i;

function renderActions(overrides: Partial<TribunalContestedActionsProps> = {}) {
  const props: TribunalContestedActionsProps = {
    point: concentration,
    caseFile,
    voices,
    isAggregate: false,
    privacy: false,
    copilotAvailable: true,
    parametriEnabled: true,
    labEnabled: true,
    onAskCopilot: vi.fn(),
    onOpenPolicyDraft: vi.fn(),
    onOpenLab: vi.fn(),
    ...overrides,
  };
  const view = render(<MantineProvider><TribunalContestedActions {...props} /></MantineProvider>);
  return { ...view, props };
}

/** A copy of the case file where the fact behind the side summary is the (sensitive) score. */
function withSensitiveFact(): { file: TribunalCaseFile; point: TribunalContestedPoint } {
  const file: TribunalCaseFile = {
    ...caseFile,
    facts: [
      ...caseFile.facts,
      {
        id: 'F99', key: 'score.health', group: 'salute', label: 'Punteggio di salute', value: 72, unit: 'score',
        formatted: '72/100', source: 'health_score', quality: 'ok', citable: true, reason: null, subject: null, sensitive: true,
      },
    ],
  };
  const point: TribunalContestedPoint = {
    ...concentration,
    text: 'Il punteggio di 72/100 e la concentrazione al 46,6%.',
    text_template: 'Il punteggio di {F99} e la concentrazione al {F5}.',
    fact_ids: ['F99', 'F5'],
  };
  return { file, point };
}

describe('buildContestedCopilotPrompt', () => {
  it('writes the point, the cited facts, both sides and the closing request (ui-spec §9)', () => {
    expect(buildContestedCopilotPrompt(concentration, caseFile, voices)).toBe(EXPECTED_C1);
  });

  it('lists the facts of the point and then of the sides once, in order of appearance', () => {
    expect(contestedFactIds(drawdown)).toEqual(['F21', 'F1']);
    const prompt = buildContestedCopilotPrompt(drawdown, caseFile, voices);
    const cited = prompt.split('\n')[1];
    expect(cited).toBe('Dati citati: Stress test «Global Financial Crisis» (2008): impatto stimato: -38,2%; Quota azionaria: 75,6%.');
    expect(prompt.split('\n')[2]).toMatch(/^Il prudente: «/);
  });

  it('proposes no instrument operation and no threshold', () => {
    for (const point of session.synthesis!.contested_points) {
      const prompt = buildContestedCopilotPrompt(point, caseFile, voices);
      expect(prompt).not.toMatch(PRESCRIPTIVE);
      expect(prompt).toContain('Nessuna indicazione di acquisto o vendita.');
      // Only numbers of the case file: every percentage in the prompt is a cited fact.
      const cited = new Set(contestedFactIds(point).map((id) => caseFile.facts.find((fact) => fact.id === id)!.formatted));
      for (const value of prompt.match(/-?\d+(?:,\d+)?%/g) ?? []) expect(cited).toContain(value);
    }
  });

  it('omits sensitive facts and hides their value in the text with Privacy Mode on', () => {
    const { file, point } = withSensitiveFact();
    const visible = buildContestedCopilotPrompt(point, file, voices);
    expect(visible).toContain('Punteggio di salute: 72/100');
    expect(visible).toContain('«Il punteggio di 72/100 e la concentrazione al 46,6%.»');

    const hidden = buildContestedCopilotPrompt(point, file, voices, { privacy: true });
    expect(hidden).not.toContain('72/100');
    expect(hidden).not.toContain('Punteggio di salute');
    expect(hidden).toContain('«Il punteggio di [dato nascosto] e la concentrazione al 46,6%.»');
    expect(hidden).toContain('Peso massimo singola posizione: 46,6%');
  });
});

describe('TribunalContestedActions', () => {
  it('shows the three actions when every destination is on', () => {
    renderActions();
    expect(screen.getByRole('button', { name: 'Approfondisci con il Copilot' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Fissa un tuo parametro/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Prova uno scenario' })).toBeInTheDocument();
    expect(screen.queryByTestId('tribunal-actions-aggregate-note')).not.toBeInTheDocument();
  });

  it('asks the Copilot with the pre-filled question', () => {
    const { props } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Approfondisci con il Copilot' }));
    expect(props.onAskCopilot).toHaveBeenCalledWith(EXPECTED_C1);
    expect(props.onOpenPolicyDraft).not.toHaveBeenCalled();
  });

  it('opens «I miei parametri» on the single metric of the point, passing only the metric code', () => {
    const { props } = renderActions({ point: drawdown });
    fireEvent.click(screen.getByRole('button', { name: 'Fissa un tuo parametro' }));
    expect(props.onOpenPolicyDraft).toHaveBeenCalledTimes(1);
    expect(props.onOpenPolicyDraft).toHaveBeenCalledWith('equity_weight_pct');
  });

  it('lets the user choose the metric when the point has more than one', async () => {
    const { props } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: /Fissa un tuo parametro/ }));
    const item = await screen.findByRole('menuitem', { name: 'Peso prime tre posizioni' });
    expect(screen.getByRole('menuitem', { name: 'Peso massimo singola posizione' })).toBeInTheDocument();
    fireEvent.click(item);
    await waitFor(() => expect(props.onOpenPolicyDraft).toHaveBeenCalledWith('top3_positions_pct'));
  });

  it('opens the Laboratorio with nothing pre-filled', () => {
    const { props } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Prova uno scenario' }));
    expect(props.onOpenLab).toHaveBeenCalledWith();
  });

  it('hides each action whose destination is off, and renders nothing when all are off', () => {
    const { rerender, props } = renderActions({ copilotAvailable: false });
    expect(screen.queryByRole('button', { name: 'Approfondisci con il Copilot' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Prova uno scenario' })).toBeInTheDocument();

    rerender(<MantineProvider><TribunalContestedActions {...props} copilotAvailable={false} parametriEnabled={false} /></MantineProvider>);
    expect(screen.queryByRole('button', { name: /Fissa un tuo parametro/ })).not.toBeInTheDocument();

    rerender(<MantineProvider><TribunalContestedActions {...props} copilotAvailable={false} parametriEnabled={false} labEnabled={false} /></MantineProvider>);
    expect(screen.queryByTestId('tribunal-contested-actions')).not.toBeInTheDocument();
  });

  it('hides «Fissa un tuo parametro» when the point is not tied to a Doctor metric', () => {
    renderActions({ point: { ...drawdown, metric_codes: [] } });
    expect(screen.queryByRole('button', { name: /Fissa un tuo parametro/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approfondisci con il Copilot' })).toBeInTheDocument();
  });

  it('keeps the three actions in the aggregate view, with the scope note', () => {
    renderActions({ isAggregate: true });
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(screen.getByTestId('tribunal-actions-aggregate-note')).toHaveTextContent('insieme dei portafogli selezionati');
  });

  it('shows no scope note in the aggregate view when only the Copilot is available', () => {
    renderActions({ isAggregate: true, parametriEnabled: false, labEnabled: false });
    expect(screen.queryByTestId('tribunal-actions-aggregate-note')).not.toBeInTheDocument();
  });

  it('labels a metric with its case-file fact, falling back to the code', () => {
    expect(metricLabelFromCaseFile('equity_weight_pct', caseFile)).toBe('Quota azionaria');
    expect(metricLabelFromCaseFile('sconosciuta', caseFile)).toBe('sconosciuta');
  });
});
