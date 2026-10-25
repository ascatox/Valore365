import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import type { MarketCalendarEvent, MarketCalendarResponse } from '../../../services/api';
import { MarketCalendarView } from './MarketCalendarCard';

const baseEvent: MarketCalendarEvent = {
  id: 'event',
  category: 'macro',
  importance: 'medium',
  title: 'Evento',
  description: null,
  day: '2026-10-28',
  starts_at: null,
  time_hint: null,
  region: null,
  tags: [],
  symbol: null,
  company: null,
  market_cap: null,
  eps_estimate: null,
  eps_actual: null,
  source_name: null,
  period: null,
  expected: null,
  previous: null,
  actual: null,
};

const event = (overrides: Partial<MarketCalendarEvent>): MarketCalendarEvent => ({ ...baseEvent, ...overrides });

const fed = event({
  id: 'fed-2026-10-28',
  category: 'central_bank',
  importance: 'high',
  title: 'Fed: decisione sui tassi',
  starts_at: '2026-10-28T18:00:00Z',
  region: 'US',
});
const microsoft = event({
  id: 'earnings-MSFT-2026-10-28',
  category: 'earnings',
  importance: 'high',
  title: 'Trimestrale Microsoft',
  starts_at: '2026-10-28T20:05:00Z',
  time_hint: 'Dopo la chiusura USA',
  region: 'US',
  tags: ['Big Tech'],
  symbol: 'MSFT',
  market_cap: 3.5e12,
  eps_estimate: 3.9,
});
const mediumEarnings = Array.from({ length: 6 }, (_, i) =>
  event({ id: `earnings-X${i}`, category: 'earnings', title: `Trimestrale Azienda ${i}`, symbol: `X${i}` }),
);

const data: MarketCalendarResponse = {
  start_date: '2026-10-26',
  end_date: '2026-10-28',
  timezone: 'Europe/Rome',
  generated_at: '2026-10-25T10:00:00Z',
  warnings: ['Calendario dei dati macroeconomici momentaneamente non disponibile.'],
  days: [
    { day: '2026-10-26', events: [] },
    { day: '2026-10-27', events: [] },
    { day: '2026-10-28', events: [fed, microsoft, ...mediumEarnings] },
  ],
};

function renderView(onSymbolClick = vi.fn()) {
  render(
    <MantineProvider>
      <MarketCalendarView data={data} today="2026-10-26" onSymbolClick={onSymbolClick} />
    </MantineProvider>,
  );
  return { onSymbolClick };
}

describe('MarketCalendarView', () => {
  it('shows days, highlights in Italian time and provider warnings', () => {
    renderView();
    expect(screen.getByText('Lunedì 26 ottobre')).toBeInTheDocument();
    expect(screen.getByText('Oggi')).toBeInTheDocument();
    expect(screen.getAllByText('Nessun evento di rilievo in calendario.')).toHaveLength(2);
    // 18:00 UTC is 19:00 in Rome after the switch to CET.
    expect(screen.getByText('ore 19:00 · USA')).toBeInTheDocument();
    expect(screen.getByText('Dopo la chiusura USA · USA · MSFT')).toBeInTheDocument();
    expect(screen.getByText('Cap. 3500 mld $ · EPS atteso 3,9')).toBeInTheDocument();
    expect(screen.getByText("Da tenere d'occhio")).toBeInTheDocument();
    expect(screen.getByText('Calendario dei dati macroeconomici momentaneamente non disponibile.')).toBeInTheDocument();
  });

  it('collapses the medium-impact tail of a busy day', () => {
    renderView();
    expect(screen.queryByText('Trimestrale Azienda 5')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Mostra altri 2'));
    expect(screen.getByText('Trimestrale Azienda 5')).toBeInTheDocument();
    expect(screen.getByText('Mostra meno')).toBeInTheDocument();
  });

  it('opens the symbol details for an earnings event', () => {
    const { onSymbolClick } = renderView();
    fireEvent.click(screen.getByLabelText('Dettagli MSFT'));
    expect(onSymbolClick).toHaveBeenCalledWith('MSFT');
  });
});
