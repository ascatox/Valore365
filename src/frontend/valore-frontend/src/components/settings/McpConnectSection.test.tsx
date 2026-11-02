import { describe, expect, it } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { McpConnectSection } from './McpConnectSection';
import { MCP_USER_GUIDE_URL, resolveMcpServerUrl } from './mcpServerUrl';

function renderSection(serverUrl?: string) {
  return render(
    <MantineProvider>
      <McpConnectSection serverUrl={serverUrl} />
    </MantineProvider>,
  );
}

describe('resolveMcpServerUrl', () => {
  it('uses the origin of an absolute API base URL, outside the /api prefix', () => {
    expect(resolveMcpServerUrl('https://api.example.com/api', 'https://app.example.com'))
      .toBe('https://api.example.com/mcp');
  });

  it('falls back to the page origin when the API base URL is relative', () => {
    expect(resolveMcpServerUrl('/api', 'http://localhost:5173')).toBe('http://localhost:5173/mcp');
  });

  it('prefers an explicit override, without trailing slash', () => {
    expect(resolveMcpServerUrl('/api', 'https://app.example.com', ' https://api.example.com/mcp/ '))
      .toBe('https://api.example.com/mcp');
  });
});

describe('McpConnectSection', () => {
  it('shows the MCP server URL with a copy button and the Claude Code command', () => {
    renderSection('https://api.example.com/mcp');

    expect(screen.getByRole('heading', { name: 'Collega Claude o ChatGPT (MCP)' })).toBeInTheDocument();
    expect(screen.getByTestId('mcp-server-url')).toHaveTextContent('https://api.example.com/mcp');
    expect(screen.getByRole('button', { name: 'Copia' })).toBeInTheDocument();
    expect(
      screen.getByText('claude mcp add --transport http valore365 https://api.example.com/mcp'),
    ).toBeInTheDocument();
  });

  it('states it is read-only and links to the user guide', () => {
    renderSection('https://api.example.com/mcp');

    expect(screen.getByText('Sola lettura')).toBeInTheDocument();
    const guide = screen.getByRole('link', { name: /Guida completa al collegamento/ });
    expect(guide).toHaveAttribute('href', MCP_USER_GUIDE_URL);
    expect(guide).toHaveAttribute('target', '_blank');
  });

  it('derives the URL from the configured API base URL by default', () => {
    renderSection();

    // In tests VITE_API_BASE_URL is unset, so the relative "/api" resolves against the page origin.
    expect(screen.getByTestId('mcp-server-url')).toHaveTextContent(`${window.location.origin}/mcp`);
  });
});
