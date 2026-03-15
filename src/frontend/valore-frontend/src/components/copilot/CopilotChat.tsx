import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Drawer,
  Group,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconMessagePlus, IconRobot, IconSend, IconTrash } from '@tabler/icons-react';
import { MessageBubble } from './MessageBubble';
import { getAuthToken } from '../../services/api';

const API_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const COPILOT_FONT = "'DM Sans', system-ui, sans-serif";

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

const STORAGE_PREFIX = 'copilot_chat_';
const MAX_CONVERSATIONS = 5;
const MAX_MESSAGES_PER_CONV = 50;

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface StoredConversation {
  id: string;
  portfolioId: number;
  messages: Message[];
  updatedAt: number; // timestamp
  preview: string;   // first user message as preview
}

function getStorageKey(portfolioId: number): string {
  return `${STORAGE_PREFIX}${portfolioId}`;
}

function loadConversations(portfolioId: number): StoredConversation[] {
  try {
    const raw = localStorage.getItem(getStorageKey(portfolioId));
    if (!raw) return [];
    const convs: StoredConversation[] = JSON.parse(raw);
    return convs.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

function saveConversations(portfolioId: number, convs: StoredConversation[]): void {
  try {
    // Keep only the latest N conversations
    const trimmed = convs
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    localStorage.setItem(getStorageKey(portfolioId), JSON.stringify(trimmed));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

function saveCurrentConversation(
  portfolioId: number,
  conversationId: string,
  messages: Message[],
): void {
  if (messages.length === 0) return;
  const convs = loadConversations(portfolioId);
  const trimmedMessages = messages.slice(-MAX_MESSAGES_PER_CONV);
  const firstUserMsg = messages.find((m) => m.role === 'user');
  const preview = firstUserMsg?.content.slice(0, 80) || 'Conversazione';

  const idx = convs.findIndex((c) => c.id === conversationId);
  const updated: StoredConversation = {
    id: conversationId,
    portfolioId,
    messages: trimmedMessages,
    updatedAt: Date.now(),
    preview,
  };

  if (idx >= 0) {
    convs[idx] = updated;
  } else {
    convs.push(updated);
  }
  saveConversations(portfolioId, convs);
}

function deleteConversation(portfolioId: number, conversationId: string): void {
  const convs = loadConversations(portfolioId).filter((c) => c.id !== conversationId);
  saveConversations(portfolioId, convs);
}

function generateId(): string {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CopilotChatProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number | null;
  portfolioIds?: number[];
  title?: string;
  quickPrompts?: string[];
  emptyStateDescription?: string;
}

const QUICK_PROMPTS = [
  'Riassumi il portafoglio',
  'Sono lontano dal target?',
  'Quanto devo investire per ribilanciare?',
  'Ho 200\u20AC/mese, come li distribuisco?',
  'Il mio portafoglio e\u0027 sano?',
  'Cosa succede se vendo il titolo piu\u0027 pesante?',
];

export function CopilotChat({
  opened,
  onClose,
  portfolioId,
  portfolioIds,
  title = 'Portfolio Copilot',
  quickPrompts = QUICK_PROMPTS,
  emptyStateDescription = 'Chiedimi qualsiasi cosa sul tuo portafoglio. Ecco qualche spunto:',
}: CopilotChatProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thinkingStatus, setThinkingStatus] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string>(generateId());
  const [showHistory, setShowHistory] = useState(false);
  const [savedConversations, setSavedConversations] = useState<StoredConversation[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const prevPortfolioRef = useRef<number | null>(portfolioId);

  // Load conversations when portfolio changes
  useEffect(() => {
    if (prevPortfolioRef.current !== portfolioId) {
      prevPortfolioRef.current = portfolioId;
      setError(null);
      if (portfolioId) {
        const convs = loadConversations(portfolioId);
        setSavedConversations(convs);
        // Resume the most recent conversation if it exists
        if (convs.length > 0) {
          setMessages(convs[0].messages);
          setConversationId(convs[0].id);
          setShowHistory(false);
        } else {
          setMessages([]);
          setConversationId(generateId());
        }
      } else {
        setMessages([]);
        setSavedConversations([]);
        setConversationId(generateId());
      }
    }
  }, [portfolioId]);

  // Refresh history list when drawer opens
  useEffect(() => {
    if (opened && portfolioId) {
      setSavedConversations(loadConversations(portfolioId));
    }
  }, [opened, portfolioId]);

  // Save conversation to localStorage after each completed exchange
  useEffect(() => {
    if (!streaming && portfolioId && messages.length > 0) {
      saveCurrentConversation(portfolioId, conversationId, messages);
      setSavedConversations(loadConversations(portfolioId));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTo({ top: viewportRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  // Abort stream on close
  useEffect(() => {
    if (!opened && abortRef.current) {
      abortRef.current.abort();
    }
  }, [opened]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || !portfolioId || streaming) return;
    setShowHistory(false);

    const userMsg: Message = { role: 'user', content: text.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setError(null);
    setStreaming(true);

    const assistantMsg: Message = { role: 'assistant', content: '' };
    setMessages([...newMessages, assistantMsg]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = await getAuthToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/copilot/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          portfolio_id: portfolioId,
          ...(portfolioIds && portfolioIds.length > 0 ? { portfolio_ids: portfolioIds } : {}),
          messages: newMessages,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(errBody || `Errore ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let accumulated = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          try {
            const event = JSON.parse(payload);
            if (event.type === 'thinking') {
              setThinkingStatus(event.content);
            } else if (event.type === 'text_delta') {
              setThinkingStatus(null);
              accumulated += event.content;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: accumulated };
                return updated;
              });
            } else if (event.type === 'error') {
              setThinkingStatus(null);
              setError(event.content);
            } else if (event.type === 'done') {
              setThinkingStatus(null);
            }
          } catch {
            // skip malformed SSE
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setError(err.message);
      }
    } finally {
      setStreaming(false);
      setThinkingStatus(null);
      abortRef.current = null;
    }
  }, [messages, portfolioId, streaming]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setError(null);
    setConversationId(generateId());
    setShowHistory(false);
  };

  const resumeConversation = (conv: StoredConversation) => {
    setMessages(conv.messages);
    setConversationId(conv.id);
    setError(null);
    setShowHistory(false);
  };

  const handleDeleteConversation = (conv: StoredConversation) => {
    if (!portfolioId) return;
    deleteConversation(portfolioId, conv.id);
    const updated = loadConversations(portfolioId);
    setSavedConversations(updated);
    // If we deleted the active conversation, start fresh
    if (conv.id === conversationId) {
      startNewChat();
    }
  };

  const clearChat = () => {
    if (portfolioId) {
      deleteConversation(portfolioId, conversationId);
      setSavedConversations(loadConversations(portfolioId));
    }
    startNewChat();
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) return `Oggi ${d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}`;
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  const hasHistory = savedConversations.length > 0;
  const otherConversations = savedConversations.filter((c) => c.id !== conversationId);

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size={isMobile ? '100%' : 'lg'}
      title={
        <Group gap="xs">
          <IconRobot size={20} />
          <Text fw={700}>{title}</Text>
          <Badge size="xs" variant="light" color="teal">AI</Badge>
        </Group>
      }
      styles={{
        body: { display: 'flex', flexDirection: 'column', height: 'calc(100% - 60px)', padding: 0, overflowX: 'hidden' },
        content: { display: 'flex', flexDirection: 'column', overflowX: 'hidden' },
        header: { zIndex: 10 },
        close: { minWidth: 36, minHeight: 36, width: 36, height: 36 },
      }}
    >
      {/* Messages */}
      <ScrollArea
        flex={1}
        px="md"
        pt="sm"
        viewportRef={viewportRef}
      >
        {messages.length === 0 && !showHistory ? (
          <Stack gap="md" py="xl" align="center">
            <Box
              style={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                background: isDark ? theme.colors.teal[9] : theme.colors.teal[0],
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <IconRobot size={28} color={isDark ? theme.colors.teal[3] : theme.colors.teal[7]} />
            </Box>
            <Text size="sm" c="dimmed" ta="center" maw={300} style={{ fontFamily: COPILOT_FONT }}>
              {emptyStateDescription}
            </Text>
            <Stack gap="xs" w="100%" maw={340}>
              {quickPrompts.map((prompt) => (
                <Button
                  key={prompt}
                  variant="light"
                  color="teal"
                  size="xs"
                  radius="xl"
                  onClick={() => sendMessage(prompt)}
                  disabled={!portfolioId || streaming}
                  styles={{ label: { whiteSpace: 'normal', textAlign: 'left', fontFamily: COPILOT_FONT } }}
                >
                  {prompt}
                </Button>
              ))}
            </Stack>

            {/* Show history link */}
            {otherConversations.length > 0 && (
              <Button
                variant="subtle"
                color="dimmed"
                size="xs"
                onClick={() => setShowHistory(true)}
                style={{ fontFamily: COPILOT_FONT }}
              >
                Conversazioni precedenti ({otherConversations.length})
              </Button>
            )}
          </Stack>
        ) : showHistory ? (
          <Stack gap="xs" py="sm">
            <Group justify="space-between" px="xs">
              <Text size="sm" fw={600} style={{ fontFamily: COPILOT_FONT }}>
                Conversazioni precedenti
              </Text>
              <Button
                variant="subtle"
                size="xs"
                color="teal"
                onClick={() => setShowHistory(false)}
                style={{ fontFamily: COPILOT_FONT }}
              >
                Indietro
              </Button>
            </Group>
            {savedConversations.map((conv) => (
              <Box
                key={conv.id}
                px="sm"
                py="xs"
                style={{
                  borderRadius: 8,
                  background: conv.id === conversationId
                    ? (isDark ? theme.colors.teal[9] : theme.colors.teal[0])
                    : (isDark ? theme.colors.dark[6] : theme.colors.gray[0]),
                  cursor: 'pointer',
                }}
              >
                <Group justify="space-between" wrap="nowrap">
                  <Box onClick={() => resumeConversation(conv)} style={{ flex: 1, cursor: 'pointer' }}>
                    <Text
                      size="sm"
                      fw={conv.id === conversationId ? 600 : 400}
                      lineClamp={1}
                      style={{ fontFamily: COPILOT_FONT }}
                    >
                      {conv.preview}
                    </Text>
                    <Text size="xs" c="dimmed" style={{ fontFamily: COPILOT_FONT }}>
                      {formatTime(conv.updatedAt)} · {conv.messages.length} msg
                    </Text>
                  </Box>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteConversation(conv);
                    }}
                    aria-label="Elimina conversazione"
                  >
                    <IconTrash size={14} />
                  </ActionIcon>
                </Group>
              </Box>
            ))}
          </Stack>
        ) : (
          <Stack gap="sm" pb="sm">
            {messages.map((msg, i) => (
              <MessageBubble
                key={i}
                role={msg.role}
                content={msg.content}
                streaming={streaming && i === messages.length - 1 && msg.role === 'assistant'}
                thinkingStatus={
                  streaming && i === messages.length - 1 && msg.role === 'assistant'
                    ? thinkingStatus
                    : null
                }
              />
            ))}
          </Stack>
        )}
      </ScrollArea>

      {/* Error */}
      {error && (
        <Box px="md" py="xs">
          <Text size="xs" c="red">{error}</Text>
        </Box>
      )}

      {/* Input */}
      <Box
        px="md"
        py="sm"
        style={{
          borderTop: `1px solid ${isDark ? theme.colors.dark[4] : theme.colors.gray[2]}`,
          background: isDark ? theme.colors.dark[7] : '#fff',
        }}
      >
        <Group gap="xs" align="flex-end">
          {messages.length > 0 && (
            <>
              <ActionIcon
                variant="subtle"
                color="teal"
                size="lg"
                onClick={startNewChat}
                disabled={streaming}
                aria-label="Nuova conversazione"
                title="Nuova conversazione"
              >
                <IconMessagePlus size={16} />
              </ActionIcon>
              <ActionIcon
                variant="subtle"
                color="gray"
                size="lg"
                onClick={clearChat}
                disabled={streaming}
                aria-label="Cancella conversazione"
                title="Cancella conversazione"
              >
                <IconTrash size={16} />
              </ActionIcon>
            </>
          )}
          {messages.length === 0 && hasHistory && !showHistory && (
            <ActionIcon
              variant="subtle"
              color="dimmed"
              size="lg"
              onClick={() => setShowHistory(true)}
              aria-label="Conversazioni precedenti"
              title="Conversazioni precedenti"
            >
              <IconMessagePlus size={16} />
            </ActionIcon>
          )}
          <Textarea
            flex={1}
            placeholder={portfolioId ? 'Chiedi al Copilot...' : 'Seleziona un portafoglio'}
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            disabled={!portfolioId || streaming}
            autosize
            minRows={1}
            maxRows={4}
            radius="xl"
            size="sm"
            styles={{ input: { fontFamily: COPILOT_FONT } }}
          />
          <ActionIcon
            variant="filled"
            color="teal"
            size="lg"
            radius="xl"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || !portfolioId || streaming}
            loading={streaming}
            aria-label="Invia messaggio"
          >
            <IconSend size={16} />
          </ActionIcon>
        </Group>
      </Box>
    </Drawer>
  );
}
