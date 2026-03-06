import { Badge, Box, Button, Drawer, Group, Stack, Text, UnstyledButton, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import type { TablerIconsProps } from '@tabler/icons-react';
import { IconBolt, IconChevronUp } from '@tabler/icons-react';

interface MobileActionItem {
  label: string;
  description: string;
  icon: React.ComponentType<TablerIconsProps>;
  onClick: () => void;
  disabled?: boolean;
  color?: string;
}

interface MobileActionSheetProps {
  opened: boolean;
  onOpen: () => void;
  onClose: () => void;
  title: string;
  badge?: string;
  primaryAction?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
  };
  items: MobileActionItem[];
}

export function MobileActionSheet({
  opened,
  onOpen,
  onClose,
  title,
  badge,
  primaryAction,
  items,
}: MobileActionSheetProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <>
      <Group
        wrap="nowrap"
        gap="xs"
        style={{
          position: 'fixed',
          left: 12,
          right: 12,
          bottom: 12,
          zIndex: 44,
          padding: 8,
          borderRadius: 24,
          background: isDark ? 'rgba(30, 41, 59, 0.94)' : 'rgba(255,255,255,0.94)',
          backdropFilter: 'blur(16px)',
          border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(148,163,184,0.22)',
          boxShadow: isDark ? '0 18px 42px rgba(0, 0, 0, 0.34)' : '0 18px 42px rgba(15, 23, 42, 0.18)',
        }}
      >
        {primaryAction && (
          <Button
            radius="xl"
            size="md"
            variant="filled"
            color="teal"
            disabled={primaryAction.disabled}
            onClick={primaryAction.onClick}
            style={{ flex: '1 1 0' }}
          >
            {primaryAction.label}
          </Button>
        )}

        <UnstyledButton
          onClick={onOpen}
          style={{
            flex: primaryAction ? '0 0 auto' : '1 1 0',
            minWidth: primaryAction ? 112 : undefined,
            borderRadius: 18,
            padding: primaryAction ? '12px 16px' : '14px 18px',
            background: isDark
              ? `linear-gradient(135deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[6]} 100%)`
              : 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
            color: '#ffffff',
            boxShadow: isDark ? '0 14px 30px rgba(0, 0, 0, 0.34)' : '0 14px 30px rgba(15, 23, 42, 0.22)',
          }}
        >
          <Group justify="space-between" wrap="nowrap" gap="sm">
            <Group gap="xs" wrap="nowrap">
              <IconBolt size={18} />
              <Box>
                <Text fw={700} size="sm">Azioni</Text>
                {!primaryAction && (
                  <Text size="xs" c="rgba(255,255,255,0.68)">
                    {title}
                  </Text>
                )}
              </Box>
            </Group>
            <IconChevronUp size={18} />
          </Group>
        </UnstyledButton>
      </Group>

      <Drawer
        opened={opened}
        onClose={onClose}
        position="bottom"
        size="82%"
        radius="24px 24px 0 0"
        title={title}
      >
        <Stack gap="sm">
          <Group gap="xs" wrap="wrap">
            {badge && (
              <Badge variant="light" color="teal" size="lg">
                {badge}
              </Badge>
            )}
            <Badge variant="outline" color="gray" size="lg">
              Flusso rapido
            </Badge>
          </Group>

          {items.map((item) => {
            const Icon = item.icon;
            return (
              <UnstyledButton
                key={item.label}
                onClick={() => {
                  onClose();
                  item.onClick();
                }}
                disabled={item.disabled}
                style={{
                  width: '100%',
                  borderRadius: 20,
                  padding: '16px 18px',
                  textAlign: 'left',
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
                  background: item.disabled
                    ? (isDark ? theme.colors.dark[6] : '#f8fafc')
                    : (isDark
                      ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
                      : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)'),
                  opacity: item.disabled ? 0.55 : 1,
                  boxShadow: item.disabled ? 'none' : (isDark ? '0 12px 28px rgba(0, 0, 0, 0.24)' : '0 12px 28px rgba(15, 23, 42, 0.07)'),
                }}
              >
                <Group justify="space-between" wrap="nowrap" gap="sm">
                  <Group wrap="nowrap" gap="sm" style={{ minWidth: 0 }}>
                    <Box
                      style={{
                        width: 42,
                        height: 42,
                        minWidth: 42,
                        borderRadius: 14,
                        display: 'grid',
                        placeItems: 'center',
                        background: item.color ?? 'linear-gradient(135deg, #0f766e 0%, #134e4a 100%)',
                        color: '#ffffff',
                      }}
                    >
                      <Icon size={18} />
                    </Box>
                    <Box style={{ minWidth: 0 }}>
                      <Text fw={700} size="sm" c={isDark ? theme.white : '#0f172a'}>{item.label}</Text>
                      <Text size="xs" c="dimmed">{item.description}</Text>
                    </Box>
                  </Group>
                </Group>
              </UnstyledButton>
            );
          })}
        </Stack>
      </Drawer>
    </>
  );
}
