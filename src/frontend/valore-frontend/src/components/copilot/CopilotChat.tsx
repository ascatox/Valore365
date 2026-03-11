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
import { IconRobot, IconSend, IconTrash } from '@tabler/icons-react';
import { MessageBubble } from './MessageBubble';
import { getAuthToken } from '../../services/api';

const API_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const COPILOT_FONT = "'DM Sans', system-ui, sans-serif";

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface CopilotChatProps {
  opened: boolean;
  onClose: () => void;
  portfolioId: number | null;
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
  title = 'Portfolio Copilot',
  quickPrompts = QUICK_PROMPTS,
  emptyStateDescription = 'Chiedimi qualsiasi cosa sul tuo portafoglio. Ecco qualche spunto:',
}: CopilotChatProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thinkingStatus, setThinkingStatus] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const prevPortfolioRef = useRef<number | null>(portfolioId);

  // Reset conversation on portfolio change
  useEffect(() => {
    if (prevPortfolioRef.current !== portfolioId) {
      setMessages([]);
      setError(null);
      prevPortfolioRef.current = portfolioId;
    }
  }, [portfolioId]);

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

  const clearChat = () => {
    setMessages([]);
    setError(null);
  };

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="lg"
      title={
        <Group gap="xs">
          <IconRobot size={20} />
          <Text fw={700}>{title}</Text>
          <Badge size="xs" variant="light" color="teal">AI</Badge>
        </Group>
      }
      styles={{
        body: { display: 'flex', flexDirection: 'column', height: 'calc(100% - 60px)', padding: 0 },
        content: { display: 'flex', flexDirection: 'column' },
      }}
    >
      {/* Messages */}
      <ScrollArea
        flex={1}
        px="md"
        pt="sm"
        viewportRef={viewportRef}
      >
        {messages.length === 0 ? (
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
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={clearChat}
              disabled={streaming}
              aria-label="Cancella conversazione"
            >
              <IconTrash size={16} />
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
