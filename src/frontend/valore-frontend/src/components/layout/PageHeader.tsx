import type { ReactNode } from 'react';
import { Box, Group, Stack, Text, Title } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  /** Mobile only: rendered inside the sticky bar, under the title row (e.g. tabs). */
  mobileBelow?: ReactNode;
  /** Mobile only: drop the title and keep just the actions (the bottom nav already names the page). */
  hideMobileTitle?: boolean;
}

export function PageHeader({ eyebrow, title, description, actions, mobileBelow, hideMobileTitle = false }: PageHeaderProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');

  if (isMobile) {
    // One compact sticky row instead of eyebrow + title + full-width cards:
    // the page name (or nothing) on the left, the page's controls on the right.
    return (
      <Box className="mobile-page-header">
        <Group justify="space-between" wrap="nowrap" gap="sm">
          {!hideMobileTitle && (
            <Title order={5} fw={800} style={{ flexShrink: 0 }}>
              {title}
            </Title>
          )}
          {actions && (
            <Box style={{ minWidth: 0, flex: hideMobileTitle ? 1 : undefined, display: 'flex', justifyContent: hideMobileTitle ? 'flex-start' : 'flex-end' }}>
              {actions}
            </Box>
          )}
        </Group>
        {mobileBelow}
      </Box>
    );
  }

  return (
    <Group justify="space-between" align="flex-end" wrap="wrap" gap="xs">
      <Stack gap={6}>
        {eyebrow && (
          <Text fw={800} tt="uppercase" size="xs" c="dimmed">
            {eyebrow}
          </Text>
        )}
        <Title order={2} fw={700}>
          {title}
        </Title>
        {description && (
          <Text c="dimmed" maw={680}>
            {description}
          </Text>
        )}
      </Stack>
      {actions}
    </Group>
  );
}
