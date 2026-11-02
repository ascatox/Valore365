import { describe, expect, it } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LandingPage } from './LandingPage';

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe('LandingPage AI Ready promotion', () => {
  it('links the hero badge to the AI Ready section', () => {
    const { container } = renderPage();

    const heroLink = screen.getByRole('link', { name: /AI Ready: scopri come collegare/i });
    expect(heroLink).toHaveAttribute('href', '#ai-ready');
    expect(container.querySelector('#ai-ready')).not.toBeNull();
  });

  it('explains the MCP connection in three read-only, OAuth-protected points', () => {
    renderPage();

    expect(
      screen.getByRole('heading', { name: 'AI Ready: collega il tuo portafoglio a Claude e ChatGPT' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Connessione via MCP' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sola lettura' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Accesso con il tuo login' })).toBeInTheDocument();
    expect(screen.getAllByRole('img', { name: 'AI Ready: compatibile con MCP' }).length).toBeGreaterThanOrEqual(2);
  });

  it('links the AI Ready section to the MCP user guide', () => {
    renderPage();

    const guide = screen.getByRole('link', { name: /Scopri come collegarlo/ });
    expect(guide).toHaveAttribute('href', 'https://github.com/ascatox/Valore365/blob/main/docs/mcp-guida-utente.md');
  });
});
