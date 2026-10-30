import { useState } from 'react';
import { Alert, Anchor, Badge, Button, Card, Group, Loader, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconNews } from '@tabler/icons-react';
import { formatTimeAgo } from '../formatters';
import { useMarketNews } from '../hooks/queries';
import type { MarketNewsItem } from '../../../services/api';

// Headlines shown before "Mostra altre": the backend already ranks them.
const VISIBLE_NEWS = 6;

const REGION_COLORS: Record<string, string> = {
  USA: 'blue',
  Europa: 'indigo',
  Italia: 'teal',
  Asia: 'grape',
  'Materie prime': 'yellow',
  Crypto: 'orange',
};

function NewsRow({ item, now }: { item: MarketNewsItem; now: Date }) {
  const meta = [item.publisher, formatTimeAgo(item.published, now)].filter(Boolean).join(' · ');

  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap" align="flex-start">
        {item.region && (
          <Badge size="xs" variant="light" color={REGION_COLORS[item.region] ?? 'gray'} style={{ flexShrink: 0 }} mt={2}>
            {item.region}
          </Badge>
        )}
        {item.link ? (
          <Anchor href={item.link} target="_blank" rel="noopener noreferrer" size="sm" fw={600} underline="hover" lineClamp={2}>
            {item.title}
          </Anchor>
        ) : (
          <Text size="sm" fw={600} lineClamp={2}>
            {item.title}
          </Text>
        )}
      </Group>
      {item.summary && (
        <Text size="xs" c="dimmed" lineClamp={2}>
          {item.summary}
        </Text>
      )}
      {meta && (
        <Text size="xs" c="dimmed" style={{ opacity: 0.8 }}>
          {meta}
        </Text>
      )}
    </Stack>
  );
}

export function MarketNewsView({ items, now = new Date() }: { items: MarketNewsItem[]; now?: Date }) {
  const [expanded, setExpanded] = useState(false);

  if (items.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Nessuna notizia disponibile al momento.
      </Text>
    );
  }

  const visible = expanded ? items : items.slice(0, VISIBLE_NEWS);
  const hidden = items.length - VISIBLE_NEWS;

  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" verticalSpacing="sm">
        {visible.map((item) => (
          <NewsRow key={`${item.related_symbol}-${item.title}`} item={item} now={now} />
        ))}
      </SimpleGrid>
      {hidden > 0 && (
        <Button variant="subtle" size="compact-xs" onClick={() => setExpanded((v) => !v)} style={{ alignSelf: 'flex-start' }}>
          {expanded ? 'Mostra meno' : `Mostra altre ${hidden}`}
        </Button>
      )}
    </Stack>
  );
}

export function MarketNewsCard() {
  const { data, isLoading, error } = useMarketNews();

  return (
    <Card withBorder radius="md" p="sm" shadow="sm">
      <Group gap="xs" wrap="nowrap" align="flex-start" mb="sm">
        <ThemeIcon variant="light" radius="md" aria-hidden>
          <IconNews size={18} />
        </ThemeIcon>
        <div>
          <Text fw={700}>Notizie dai mercati</Text>
          <Text size="xs" c="dimmed">
            Le principali notizie su borse internazionali, materie prime e crypto
          </Text>
        </div>
      </Group>

      {isLoading && !data && (
        <Group gap="xs">
          <Loader size="xs" />
          <Text size="sm" c="dimmed">
            Caricamento notizie...
          </Text>
        </Group>
      )}
      {error && !data && (
        <Alert color="red" variant="light">
          {error instanceof Error ? error.message : 'Errore caricamento notizie'}
        </Alert>
      )}
      {data && <MarketNewsView items={data.items} />}
    </Card>
  );
}
