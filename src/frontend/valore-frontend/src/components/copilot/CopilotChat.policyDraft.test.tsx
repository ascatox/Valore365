import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { stubLayoutApis } from '../../test/pageHarness';
import { STORAGE_KEYS } from '../dashboard/constants';
import { policyRead, preview } from '../doctor/policy/testFixtures';
import { CopilotChat } from './CopilotChat';

function sse(events: unknown[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('CopilotChat policy_draft', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the draft card, saves nothing until «Conferma e salva», then posts the token', async () => {
    const draft = { portfolio_ids: [1], preview: preview() };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/copilot/chat')) {
        return sse([
          { type: 'text_delta', content: 'Ecco una bozza dei tuoi parametri.' },
          { type: 'policy_draft', content: JSON.stringify(draft) },
          { type: 'done' },
        ]);
      }
      if (url.endsWith('/doctor/policies') && init?.method === 'POST') {
        return new Response(JSON.stringify(policyRead({ current_version: 4 })), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const onPolicySaved = vi.fn();
    render(
      <MantineProvider>
        <CopilotChat opened onClose={() => {}} portfolioId={1} pageContext="doctor" quickPrompts={['Imposta un limite del 50%']} onPolicySaved={onPolicySaved} />
      </MantineProvider>,
    );

    fireEvent.click(screen.getByText('Imposta un limite del 50%'));
    expect(await screen.findByTestId('policy-draft-card')).toBeInTheDocument();
    expect(screen.getByText('Ecco una bozza dei tuoi parametri.')).toBeInTheDocument();
    const policyPosts = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/doctor/policies'));
    expect(policyPosts()).toHaveLength(0);
    // The confirmation token never reaches the stored history.
    await waitFor(() => expect(window.localStorage.getItem('copilot_chat_1')).not.toBeNull());
    expect(window.localStorage.getItem('copilot_chat_1')).not.toContain('tok-123');

    fireEvent.click(screen.getByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onPolicySaved).toHaveBeenCalled());
    expect(policyPosts()).toHaveLength(1);
    expect(JSON.parse(String((policyPosts()[0][1] as RequestInit).body))).toMatchObject({ confirmation_token: 'tok-123', base_version: 3 });
  });
});

describe('CopilotChat Privacy Mode and draft → editor', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubChat(events: unknown[]) {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      String(input).endsWith('/copilot/chat') ? sse(events) : new Response('{}', { status: 200 })
    )));
  }

  it('masks € amounts in assistant messages on display only, on any page', async () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    stubChat([{ type: 'text_delta', content: 'Hai 58.250 € in VWRA (46,6%) e **€ 1.200** di liquidità.' }, { type: 'done' }]);
    render(
      <MantineProvider>
        <CopilotChat opened onClose={() => {}} portfolioId={1} pageContext="dashboard" quickPrompts={['Quanto ho investito in 10.000 € di ETF?']} />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByText('Quanto ho investito in 10.000 € di ETF?'));
    expect(await screen.findByText(/Hai \*{6} in VWRA \(46,6%\) e/)).toBeInTheDocument();
    expect(screen.queryByText(/58\.250/)).not.toBeInTheDocument();
    expect(screen.queryByText(/1\.200/)).not.toBeInTheDocument();
    // The user's own text is shown as typed, and stored messages are unchanged.
    expect(screen.getByText('Quanto ho investito in 10.000 € di ETF?')).toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.getItem('copilot_chat_1')).toContain('58.250 €'));
  });

  it('does not mask assistant amounts when Privacy Mode is off', async () => {
    stubChat([{ type: 'text_delta', content: 'Hai 58.250 € in VWRA.' }, { type: 'done' }]);
    render(
      <MantineProvider>
        <CopilotChat opened onClose={() => {}} portfolioId={1} pageContext="dashboard" quickPrompts={['Riassumi']} />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByText('Riassumi'));
    expect(await screen.findByText('Hai 58.250 € in VWRA.')).toBeInTheDocument();
  });

  it.each([
    [[1], true],
    [[1, 2], false],
  ])('offers «Apri nell\'editor» only for a draft of the chat scope (draft %j → %s)', async (ids, offered) => {
    stubChat([{ type: 'policy_draft', content: JSON.stringify({ portfolio_ids: ids, preview: preview() }) }, { type: 'done' }]);
    const onOpen = vi.fn();
    render(
      <MantineProvider>
        <CopilotChat
          opened onClose={() => {}} portfolioId={1} pageContext="doctor" quickPrompts={['Bozza']}
          onOpenPolicyDraft={onOpen} portfolioNames={new Map([[1, 'Core'], [2, 'Pensione']])}
        />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByText('Bozza'));
    expect(await screen.findByTestId('policy-draft-card')).toHaveTextContent(ids.length > 1 ? 'Vista aggregata: Core, Pensione' : 'Portafoglio Core');
    const button = screen.queryByRole('button', { name: "Apri nell'editor" });
    if (offered) {
      fireEvent.click(button!);
      expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ portfolio_ids: [1] }));
    } else {
      expect(button).not.toBeInTheDocument();
    }
  });
});

