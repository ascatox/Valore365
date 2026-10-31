import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { stubLayoutApis } from '../../test/pageHarness';
import { CopilotChat } from './CopilotChat';

function renderChat(props: { portfolioId: number | null; portfolioIds?: number[] }) {
  const fetchMock = vi.fn(async () => new Response('Copilot non disponibile', { status: 503 }));
  vi.stubGlobal('fetch', fetchMock);
  render(
    <MantineProvider>
      <CopilotChat opened onClose={() => {}} pageContext="dashboard" quickPrompts={['Riassumi il portafoglio']} {...props} />
    </MantineProvider>,
  );
  return fetchMock;
}

async function askAndGetBody(fetchMock: ReturnType<typeof renderChat>) {
  fireEvent.click(screen.getByText('Riassumi il portafoglio'));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toMatch(/\/copilot\/chat$/);
  return JSON.parse(String(init.body));
}

describe('CopilotChat scope', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the portfolio_ids of an aggregate scope and keeps its history apart', async () => {
    const fetchMock = renderChat({ portfolioId: 1, portfolioIds: [2, 1] });
    const body = await askAndGetBody(fetchMock);

    expect(body.portfolio_id).toBe(1);
    expect(body.portfolio_ids).toEqual([2, 1]);
    expect(body.page_context).toBe('dashboard');
    await waitFor(() => expect(window.localStorage.getItem('copilot_chat_aggregate_1_2')).not.toBeNull());
    expect(window.localStorage.getItem('copilot_chat_1')).toBeNull();
  });

  it('sends only portfolio_id for a single portfolio', async () => {
    const fetchMock = renderChat({ portfolioId: 4 });
    const body = await askAndGetBody(fetchMock);

    expect(body.portfolio_id).toBe(4);
    expect(body).not.toHaveProperty('portfolio_ids');
    await waitFor(() => expect(window.localStorage.getItem('copilot_chat_4')).not.toBeNull());
  });
});
