import type { ReactNode } from 'react';
import { Group, Stack, Text, Title } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');

  return (
    <Group justify="space-between" align="flex-end" wrap="wrap" gap="xs">
      <Stack gap={6}>
        {eyebrow && (
          <Text fw={800} tt="uppercase" size="xs" c="dimmed">
            {eyebrow}
          </Text>
        )}
        <Title order={isMobile ? 4 : 2} fw={isMobile ? 800 : 700}>
          {title}
        </Title>
        {description && !isMobile && (
          <Text c="dimmed" maw={680}>
            {description}
          </Text>
        )}
      </Stack>
      {actions}
    </Group>
  );
}
