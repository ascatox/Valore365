import { Badge, Box, Group, ScrollArea, Stack, Text, ThemeIcon } from '@mantine/core';
import type { KpiStatCardProps } from '../dashboard/types';

interface DashboardMobileKpiCarouselProps {
  items: KpiStatCardProps[];
}

export function DashboardMobileKpiCarousel({ items }: DashboardMobileKpiCarouselProps) {
  return (
    <ScrollArea offsetScrollbars scrollbarSize={0} type="never">
      <Group wrap="nowrap" gap="sm" style={{ paddingBottom: 6 }}>
        {items.map(({ label, value, color, icon: Icon, iconColor }) => (
          <Box
            key={label}
            style={{
              minWidth: 244,
              borderRadius: 24,
              padding: 18,
              background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              border: '1px solid #e2e8f0',
              boxShadow: '0 16px 32px rgba(15, 23, 42, 0.08)',
              scrollSnapAlign: 'start',
            }}
          >
            <Stack gap="lg">
              <Group justify="space-between" align="center" wrap="nowrap">
                <Text size="xs" fw={700} tt="uppercase" c="#64748b" style={{ letterSpacing: 0.8 }}>
                  {label}
                </Text>
                {Icon && (
                  <ThemeIcon color={iconColor ?? 'blue'} variant="light" size="lg" radius="xl">
                    <Icon size={18} />
                  </ThemeIcon>
                )}
              </Group>
              <Text fw={800} size="1.7rem" c={color ?? '#0f172a'} style={{ lineHeight: 1.05 }}>
                {value}
              </Text>
              <Badge
                variant="light"
                color={color ? undefined : 'teal'}
                radius="xl"
                styles={{ root: { alignSelf: 'flex-start' } }}
              >
                Focus
              </Badge>
            </Stack>
          </Box>
        ))}
      </Group>
    </ScrollArea>
  );
}
