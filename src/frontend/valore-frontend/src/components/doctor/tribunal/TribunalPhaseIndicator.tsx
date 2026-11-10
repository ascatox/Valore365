import { Stepper, Text } from '@mantine/core';
import type { TribunalPhase } from '../../../services/api/tribunalTypes';
import { PHASE_STEPS, phaseStepIndex } from './tribunalFormat';

interface TribunalPhaseIndicatorProps {
  phase: TribunalPhase | null;
  hasCaseFile: boolean;
  completed: boolean;
  completedPhases?: readonly TribunalPhase[];
  compact?: boolean;
}

/** Fasi della seduta: Fascicolo → Apertura → Replica → Sintesi (ui-spec §3, §10). */
export function TribunalPhaseIndicator({ phase, hasCaseFile, completed, completedPhases = [], compact = false }: TribunalPhaseIndicatorProps) {
  const active = phaseStepIndex(phase, hasCaseFile, completed, completedPhases);

  return (
    <nav aria-label="Fasi della seduta" data-testid="tribunal-phases" data-active-step={active}>
      <Stepper
        active={active}
        size="xs"
        iconSize={compact ? 22 : 26}
        allowNextStepsSelect={false}
        styles={{
          steps: { flexWrap: 'nowrap' },
          step: { minWidth: 0 },
          separator: { marginInline: compact ? 4 : undefined, minWidth: 8 },
          stepBody: { marginInlineStart: compact ? 4 : undefined },
        }}
      >
        {PHASE_STEPS.map((label, index) => (
          <Stepper.Step
            key={label}
            label={compact ? undefined : <Text size="xs" fw={index === active ? 700 : 500} style={{ whiteSpace: 'nowrap' }}>{label}</Text>}
            aria-current={index === active ? 'step' : undefined}
            aria-label={label}
            data-step={label}
          />
        ))}
      </Stepper>
      {compact && (
        <Text size="xs" c="dimmed" mt={6} data-testid="tribunal-phase-label">
          {active >= PHASE_STEPS.length
            ? `Fasi completate: ${PHASE_STEPS.join(' → ')}`
            : `Fase ${active + 1} di ${PHASE_STEPS.length}: ${PHASE_STEPS[active]}`}
        </Text>
      )}
    </nav>
  );
}
