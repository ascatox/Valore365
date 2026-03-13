import { Badge, Box, Group, ScrollArea, Stack, Text, ThemeIcon, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useElementSize } from '@mantine/hooks';
import type { KpiStatCardProps } from '../dashboard/types';
import { MiniGauge } from '../dashboard/summary/MiniGauge';

interface DashboardMobileKpiCarouselProps {
  items: KpiStatCardProps[];
}

export function DashboardMobileKpiCarousel({ items }: DashboardMobileKpiCarouselProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const { ref, width: containerWidth } = useElementSize();

  return (
    <div ref={ref}>
    <ScrollArea scrollbarSize={0} type="never">
      <Group wrap="nowrap" gap="sm" style={{ paddingBottom: 6, scrollSnapType: 'x mandatory' }}>
        {items.map(({ label, value, color, icon: Icon, iconColor, subtitle, subtitleColor, gaugeValue }) => (
          <Box
            key={label}
            style={{
              width: containerWidth || '100%',
              minWidth: containerWidth || 244,
              flexShrink: 0,
              borderRadius: 24,
              padding: 18,
              background: isDark
                ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
              boxShadow: isDark ? '0 16px 32px rgba(0, 0, 0, 0.28)' : '0 16px 32px rgba(15, 23, 42, 0.08)',
              scrollSnapAlign: 'start',
            }}
          >
            <Stack gap="lg">
              <Group justify="space-between" align="center" wrap="nowrap">
                <Text size="xs" fw={700} tt="uppercase" c={isDark ? theme.colors.gray[4] : '#64748b'} style={{ letterSpacing: 0.8 }}>
                  {label}
                </Text>
                {Icon && (
                  <ThemeIcon color={iconColor ?? 'blue'} variant="light" size="lg" radius="xl">
                    <Icon size={18} />
                  </ThemeIcon>
                )}
              </Group>
              <Group justify="space-between" align="flex-end" wrap="nowrap">
                <Text fw={800} size="1.3rem" c={color ?? (isDark ? theme.white : '#0f172a')} style={{ lineHeight: 1.15 }}>
                  {value}
                </Text>
                {gaugeValue != null && <MiniGauge value={gaugeValue} size={56} />}
              </Group>
              {subtitle ? (
                <Text fw={800} size="1.3rem" c={subtitleColor ?? (isDark ? theme.white : '#0f172a')} style={{ lineHeight: 1.15 }}>
                  {subtitle}
                </Text>
              ) : (
                <Badge
                  variant="light"
                  color={color ? undefined : 'teal'}
                  radius="xl"
                  styles={{ root: { alignSelf: 'flex-start' } }}
                >
                  Focus
                </Badge>
              )}
            </Stack>
          </Box>
        ))}
      </Group>
    </ScrollArea>
    </div>
  );
}
