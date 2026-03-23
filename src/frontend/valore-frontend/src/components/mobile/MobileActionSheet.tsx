import { Badge, Box, Drawer, Group, Stack, Text, UnstyledButton, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import type { CSSProperties } from 'react';
import { IconBolt, IconChevronUp } from '@tabler/icons-react';
import { MobileBottomControl } from './MobileBottomControl';

interface MobileActionItem {
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: string | number; className?: string; style?: CSSProperties }>;
  onClick: () => void;
  disabled?: boolean;
  color?: string;
}

interface MobileActionSheetProps {
  opened: boolean;
  onOpen: () => void;
  onClose: () => void;
  title: string;
  bottomOffset?: number;
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
  bottomOffset = 12,
  badge,
  primaryAction,
  items,
}: MobileActionSheetProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <>
      <MobileBottomControl
        bottomOffset={bottomOffset}
        leftAction={primaryAction ? {
          label: primaryAction.label,
          onClick: primaryAction.onClick,
          disabled: primaryAction.disabled,
          variant: 'filled',
        } : undefined}
        rightAction={{
          label: 'Azioni',
          onClick: onOpen,
          icon: IconBolt,
          description: title,
          variant: 'dark',
          rightSection: <IconChevronUp size={18} />,
        }}
      />

      <Drawer
        opened={opened}
        onClose={onClose}
        position="bottom"
        size="82%"
        radius="24px 24px 0 0"
        title={title}
        styles={{
          content: { paddingBottom: 'var(--safe-area-bottom)' },
          body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
        }}
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
                        width: 44,
                        height: 44,
                        minWidth: 44,
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
