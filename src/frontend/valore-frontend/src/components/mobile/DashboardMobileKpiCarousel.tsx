import { useState } from 'react';
import { Box, Group, Text } from '@mantine/core';
import type { KpiStatCardProps } from '../dashboard/types';

interface DashboardMobileKpiCarouselProps {
  items: KpiStatCardProps[];
}

// Cards take ~44% of the width so the next one peeks in, which tells the
// user the row scrolls; the dots below track the position.
export function DashboardMobileKpiCarousel({ items }: DashboardMobileKpiCarouselProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget;
    const card = el.firstElementChild as HTMLElement | null;
    if (!card) return;
    const step = card.offsetWidth + 8;
    setActiveIndex(Math.min(items.length - 1, Math.round(el.scrollLeft / step)));
  };

  if (!items.length) return null;

  return (
    <Box>
      <Box
        onScroll={handleScroll}
        style={{
          display: 'flex',
          gap: 8,
          overflowX: 'auto',
          scrollSnapType: 'x mandatory',
          scrollbarWidth: 'none',
          marginRight: 'calc(-2 * var(--mantine-spacing-xs))',
          paddingRight: 'calc(2 * var(--mantine-spacing-xs))',
        }}
      >
        {items.map(({ label, value, color }) => (
          <Box
            key={label}
            style={{
              flex: '0 0 44%',
              scrollSnapAlign: 'start',
              borderRadius: 14,
              padding: '10px 12px',
              background: 'var(--mantine-color-body)',
              border: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Text size="xs" fw={700} tt="uppercase" c="dimmed" truncate="end" style={{ letterSpacing: 0.6 }}>
              {label}
            </Text>
            <Text fw={700} size="md" c={color} truncate="end">
              {value}
            </Text>
          </Box>
        ))}
      </Box>
      {items.length > 2 && (
        <Group gap={4} justify="center" mt={8} aria-hidden>
          {items.map((item, index) => (
            <Box
              key={item.label}
              style={{
                width: index === activeIndex ? 14 : 5,
                height: 5,
                borderRadius: 3,
                background: index === activeIndex ? 'var(--mantine-primary-color-filled)' : 'var(--mantine-color-default-border)',
                transition: 'width 150ms ease',
              }}
            />
          ))}
        </Group>
      )}
    </Box>
  );
}
