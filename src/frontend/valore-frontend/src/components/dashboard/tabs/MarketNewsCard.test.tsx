import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { MarketNewsItem } from '../../../services/api';
import { MarketNewsView } from './MarketNewsCard';

const NOW = new Date('2026-10-29T15:00:00Z');

const news = (overrides: Partial<MarketNewsItem>): MarketNewsItem => ({
  title: 'Notizia',
  publisher: null,
  link: null,
  published: null,
  related_symbol: '^GSPC',
  region: null,
  summary: null,
  ...overrides,
});

const items: MarketNewsItem[] = [
  news({
    title: 'Wall Street apre in rialzo',
    publisher: 'Reuters',
    link: 'https://example.com/wall-street',
    published: '2026-10-29T14:45:00Z',
    region: 'USA',
    summary: 'Gli indici americani salgono dopo i dati sul lavoro.',
  }),
  news({ title: 'La BCE lascia i tassi invariati', published: '2026-10-29T12:00:00Z', region: 'Europa', related_symbol: '^STOXX50E' }),
  ...Array.from({ length: 6 }, (_, i) => news({ title: `Notizia Asia ${i}`, region: 'Asia', related_symbol: '^N225' })),
];

function renderView(list = items) {
  render(
    <MantineProvider>
      <MarketNewsView items={list} now={NOW} />
    </MantineProvider>,
  );
}

describe('MarketNewsView', () => {
  it('shows headline, region, summary, source and age', () => {
    renderView();
    const link = screen.getByRole('link', { name: 'Wall Street apre in rialzo' });
    expect(link).toHaveAttribute('href', 'https://example.com/wall-street');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.getByText('USA')).toBeInTheDocument();
    expect(screen.getByText('Gli indici americani salgono dopo i dati sul lavoro.')).toBeInTheDocument();
    expect(screen.getByText('Reuters · 15m fa')).toBeInTheDocument();
    expect(screen.getByText('3h fa')).toBeInTheDocument();
  });

  it('collapses the tail of the list', () => {
    renderView();
    expect(screen.queryByText('Notizia Asia 5')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Mostra altre 2'));
    expect(screen.getByText('Notizia Asia 5')).toBeInTheDocument();
    expect(screen.getByText('Mostra meno')).toBeInTheDocument();
  });

  it('shows an empty state without news', () => {
    renderView([]);
    expect(screen.getByText('Nessuna notizia disponibile al momento.')).toBeInTheDocument();
  });
});
