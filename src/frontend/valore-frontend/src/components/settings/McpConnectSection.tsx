import { Alert, Anchor, Button, Code, CopyButton, Group, List, Stack, Text, Title } from '@mantine/core';
import { IconCheck, IconCopy, IconExternalLink, IconLock } from '@tabler/icons-react';
import { MCP_USER_GUIDE_URL, getMcpServerUrl } from './mcpServerUrl';

const CLIENT_STEPS = [
  {
    client: 'Claude (web, app e Desktop)',
    steps: 'Settings → Connectors → Add custom connector, incolla l’URL, poi Connect e accedi con Valore365.',
  },
  {
    client: 'ChatGPT',
    steps: 'Settings → Apps & Connectors, attiva la Developer mode e crea un connettore con l’URL e autenticazione OAuth (disponibilità in base al piano).',
  },
];

export function McpConnectSection({ serverUrl = getMcpServerUrl() }: { serverUrl?: string }) {
  const claudeCodeCommand = `claude mcp add --transport http valore365 ${serverUrl}`;

  return (
    <Stack gap="lg">
      <Title order={3}>Collega Claude o ChatGPT (MCP)</Title>
      <Text size="sm" c="dimmed">
        Fai domande sul tuo portafoglio direttamente dal tuo assistente AI. Aggiungi Valore365 come
        connettore personalizzato e autorizza l’accesso con il tuo login.
      </Text>

      <Stack gap={6}>
        <Text fw={500} size="sm">URL del server MCP</Text>
        <Group gap="sm" wrap="nowrap" align="center">
          <Code
            data-testid="mcp-server-url"
            style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', padding: '8px 10px' }}
          >
            {serverUrl}
          </Code>
          <CopyButton value={serverUrl}>
            {({ copied, copy }) => (
              <Button
                variant="light"
                color={copied ? 'teal' : 'blue'}
                leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                onClick={copy}
              >
                {copied ? 'Copiato' : 'Copia'}
              </Button>
            )}
          </CopyButton>
        </Group>
      </Stack>

      <Stack gap="xs">
        <Text fw={500} size="sm">Come collegarlo</Text>
        <List size="sm" spacing="xs">
          {CLIENT_STEPS.map(({ client, steps }) => (
            <List.Item key={client}>
              <Text span fw={600} size="sm">{client}:</Text> {steps}
            </List.Item>
          ))}
          <List.Item>
            <Text span fw={600} size="sm">Claude Code:</Text> esegui{' '}
            <Code style={{ overflowWrap: 'anywhere' }}>{claudeCodeCommand}</Code>, poi <Code>/mcp</Code> per il login.
          </List.Item>
        </List>
      </Stack>

      <Alert variant="light" color="teal" icon={<IconLock size={18} />} title="Sola lettura" style={{ maxWidth: 560 }}>
        L’assistente può leggere portafogli, posizioni e analisi, ma non può creare, modificare o
        cancellare nulla. I dati letti vengono inviati al provider AI che scegli (Anthropic o OpenAI) e
        puoi scollegare il connettore in qualsiasi momento dal tuo client.
      </Alert>

      <Anchor href={MCP_USER_GUIDE_URL} target="_blank" rel="noreferrer" size="sm">
        <Group gap={4} component="span" wrap="nowrap">
          Guida completa al collegamento
          <IconExternalLink size={14} />
        </Group>
      </Anchor>
    </Stack>
  );
}
