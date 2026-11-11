import { useId, useState } from 'react';
import { Collapse, Group, Paper, Stack, Text, ThemeIcon, UnstyledButton } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { IconChevronDown, IconCircleCheck, IconHourglassLow, IconShieldCheck } from '@tabler/icons-react';
import { doctorScopeFingerprint } from '../../services/api/doctor';
import { getAuditorSummary, type AuditorArea, type AuditorSummary } from '../../services/api/auditor';

/*
 * «Calcoli verificati»: esito dei controlli notturni sui numeri del Doctor
 * (docs/auditor/architecture.md §6.1, §7.3). Discreto per scelta: una riga che
 * si apre sull'elenco dei controlli per area. Nessun id di regola, nessun
 * valore, nessun allarme: se un controllo non torna il testo dice soltanto che
 * un calcolo è in verifica e in quale area. Senza una corsa recente (48 ore,
 * deciso dal backend) o in caso di errore non compare nulla.
 *
 * Privacy Mode: l'indicatore non mostra importi, pesi né simboli, solo titoli
 * dei controlli, conteggi e la data della verifica, quindi non c'è nulla da
 * mascherare. Colori solo dal tema Mantine (`teal` è il colore del tema scelto).
 */

export const auditorQueryKeys = {
  summary: (fingerprint: string) => ['auditor', 'summary', fingerprint] as const,
};

export function formatAuditDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' });
}

const checksLabel = (count: number) => (count === 1 ? '1 controllo superato' : `${count} controlli superati`);

function joinLabels(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? '';
  return `${labels.slice(0, -1).join(', ')} e ${labels[labels.length - 1]}`;
}

/** Testo neutro per i controlli in verifica: quanti e in quale area, niente di più. */
export function inReviewText(summary: Pick<AuditorSummary, 'checks_in_review' | 'areas'>): string | null {
  if (summary.checks_in_review <= 0) return null;
  const areas = summary.areas.filter((area) => area.status === 'in_review').map((area) => area.label);
  const subject = summary.checks_in_review === 1 ? 'Un calcolo è in verifica' : `${summary.checks_in_review} calcoli sono in verifica`;
  const where = areas.length ? (areas.length === 1 ? `nell'area ${areas[0]}` : `nelle aree ${joinLabels(areas)}`) : '';
  return `${subject}${where ? ` ${where}` : ''}`;
}

function AreaGroup({ area }: { area: AuditorArea }) {
  return (
    <Stack gap={6} data-testid="audit-area" data-status={area.status}>
      <Text size="sm" fw={700}>{area.label}</Text>
      <Stack gap={4} component="ul" m={0} p={0} style={{ listStyle: 'none' }}>
        {area.checks.map((check, index) => (
          <Group key={`${check.title}-${index}`} component="li" gap={8} wrap="nowrap" align="flex-start" data-status={check.status}>
            <ThemeIcon
              size={18}
              radius="xl"
              variant="light"
              color={check.status === 'passed' ? 'teal' : 'gray'}
              style={{ flexShrink: 0, marginTop: 1 }}
              aria-hidden="true"
            >
              {check.status === 'passed' ? <IconCircleCheck size={12} /> : <IconHourglassLow size={12} />}
            </ThemeIcon>
            <Text size="sm" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
              {check.title}
              <Text span size="xs" c="dimmed">{check.status === 'passed' ? ' · superato' : ' · in verifica'}</Text>
            </Text>
          </Group>
        ))}
      </Stack>
    </Stack>
  );
}

/** Vista pura (stati coperti dai test); `AuditIndicator` la collega all'API. */
export function AuditIndicatorView({ summary, defaultOpened = false }: { summary: AuditorSummary | null | undefined; defaultOpened?: boolean }) {
  const [opened, setOpened] = useState(defaultOpened);
  const panelId = useId();
  if (!summary?.available || !summary.run_finished_at) return null;
  const date = formatAuditDate(summary.run_finished_at);
  const review = inReviewText(summary);

  return (
    <Paper withBorder radius="lg" px="sm" py={6} data-testid="audit-indicator" data-state={review ? 'in_review' : 'passed'}>
      <UnstyledButton
        onClick={() => setOpened((value) => !value)}
        aria-expanded={opened}
        aria-controls={panelId}
        w="100%"
        style={{ borderRadius: 'var(--mantine-radius-md)' }}
      >
        <Group gap={8} wrap="nowrap" align="flex-start">
          <ThemeIcon size={22} radius="xl" variant="light" color="teal" style={{ flexShrink: 0 }} aria-hidden="true">
            <IconShieldCheck size={14} />
          </ThemeIcon>
          <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
            <Group gap={6} wrap="wrap" style={{ rowGap: 0 }}>
              <Text size="sm" fw={600} data-testid="audit-indicator-label">
                {`Calcoli verificati: ${checksLabel(summary.checks_passed)}`}
              </Text>
              {date && <Text size="xs" c="dimmed">{`Ultima verifica ${date}`}</Text>}
            </Group>
            {review && (
              <Text size="xs" c="dimmed" data-testid="audit-indicator-review">{review}</Text>
            )}
          </Stack>
          <IconChevronDown
            size={16}
            aria-hidden="true"
            style={{ flexShrink: 0, marginTop: 3, transition: 'transform 150ms ease', transform: opened ? 'rotate(180deg)' : undefined }}
          />
        </Group>
      </UnstyledButton>
      <Collapse in={opened} id={panelId}>
        <Stack gap="md" pt="sm" pb={6} data-testid="audit-indicator-panel">
          <Text size="xs" c="dimmed">
            Ogni notte ricalcoliamo in modo indipendente i numeri che vedi e li confrontiamo con quelli mostrati.
            {review ? ' Un calcolo in verifica è già all’attenzione del team: non devi fare nulla.' : ''}
          </Text>
          {summary.areas.map((area) => <AreaGroup key={area.area} area={area} />)}
        </Stack>
      </Collapse>
    </Paper>
  );
}

/** Indicatore per lo scope del Doctor (portafoglio singolo o vista aggregata). */
export function AuditIndicator({ portfolioIds }: { portfolioIds: number[] }) {
  const fingerprint = doctorScopeFingerprint(portfolioIds);
  const query = useQuery({
    queryKey: auditorQueryKeys.summary(fingerprint),
    queryFn: () => getAuditorSummary(portfolioIds),
    enabled: portfolioIds.length > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  if (query.isError) return null;
  return <AuditIndicatorView key={fingerprint} summary={query.data} />;
}
