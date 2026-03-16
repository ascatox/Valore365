import { Anchor, Box, Group, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconExternalLink, IconNews } from '@tabler/icons-react';
import { useMarketNews } from '../hooks/queries';
import type { MarketNewsItem } from '../../../services/api';

const ANIMATION_DURATION_PER_ITEM = 5; // seconds per item (news needs more time to read)

function timeAgo(published: string | null): string {
  if (!published) return '';
  try {
    const date = new Date(published);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'ora';
    if (diffMin < 60) return `${diffMin}m fa`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h fa`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}g fa`;
  } catch {
    return '';
  }
}

function NewsItem({ item, isDark }: { item: MarketNewsItem; isDark: boolean }) {
  const theme = useMantineTheme();
  const separatorColor = isDark ? theme.colors.dark[4] : '#dee2e6';

  return (
    <Group
      gap={8}
      wrap="nowrap"
      style={{
        padding: '0 24px',
        flexShrink: 0,
        userSelect: 'none',
        borderRight: `1px solid ${separatorColor}`,
      }}
    >
      <IconNews size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
      {item.link ? (
        <Anchor
          href={item.link}
          target="_blank"
          rel="noopener noreferrer"
          size="xs"
          fw={600}
          underline="hover"
          style={{ whiteSpace: 'nowrap' }}
          onClick={(e) => e.stopPropagation()}
        >
          {item.title} <IconExternalLink size={10} style={{ verticalAlign: 'middle', opacity: 0.6 }} />
        </Anchor>
      ) : (
        <Text size="xs" fw={600} style={{ whiteSpace: 'nowrap' }}>
          {item.title}
        </Text>
      )}
      {item.publisher && (
        <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
          {item.publisher}
        </Text>
      )}
      {item.published && (
        <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap', opacity: 0.7 }}>
          {timeAgo(item.published)}
        </Text>
      )}
    </Group>
  );
}

export function NewsTicker() {
  const { data } = useMarketNews();
  const colorScheme = useComputedColorScheme('light');
  const theme = useMantineTheme();
  const isDark = colorScheme === 'dark';

  const items: MarketNewsItem[] = data?.items ?? [];

  if (items.length === 0) return null;

  const duration = items.length * ANIMATION_DURATION_PER_ITEM;
  const bgColor = isDark ? theme.colors.dark[7] : '#ffffff';
  const borderColor = isDark ? theme.colors.dark[5] : '#e9ecef';

  return (
    <Box
      style={{
        overflow: 'hidden',
        position: 'relative',
        borderRadius: 8,
        background: bgColor,
        border: `1px solid ${borderColor}`,
      }}
    >
      {/* Fade edges */}
      <Box
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          width: 40,
          zIndex: 1,
          background: `linear-gradient(to right, ${bgColor}, transparent)`,
          pointerEvents: 'none',
        }}
      />
      <Box
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          width: 40,
          zIndex: 1,
          background: `linear-gradient(to left, ${bgColor}, transparent)`,
          pointerEvents: 'none',
        }}
      />

      <Box
        className="news-ticker-track"
        style={{
          display: 'flex',
          alignItems: 'center',
          width: 'max-content',
          animation: `news-scroll ${duration}s linear infinite`,
          padding: '6px 0',
        }}
      >
        {items.map((item, i) => (
          <NewsItem key={`a-${i}`} item={item} isDark={isDark} />
        ))}
        {items.map((item, i) => (
          <NewsItem key={`b-${i}`} item={item} isDark={isDark} />
        ))}
      </Box>

      <style>{`
        @keyframes news-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .news-ticker-track:hover {
          animation-play-state: paused !important;
        }
        @media (prefers-reduced-motion: reduce) {
          .news-ticker-track {
            animation: none !important;
          }
        }
      `}</style>
    </Box>
  );
}
