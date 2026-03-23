import { Button, Group, Portal, Text, UnstyledButton, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import type { CSSProperties, ReactNode } from 'react';

interface MobileBottomControlAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  icon?: React.ComponentType<{ size?: string | number; className?: string; style?: CSSProperties }>;
  description?: string;
  variant?: 'filled' | 'dark';
  grow?: boolean;
  rightSection?: ReactNode;
}

interface MobileBottomControlProps {
  bottomOffset?: number;
  leftAction?: MobileBottomControlAction;
  rightAction: MobileBottomControlAction;
}

function isFilledAction(action: MobileBottomControlAction | undefined): action is MobileBottomControlAction {
  return !!action && (action.variant ?? 'filled') === 'filled';
}

function isGrowingAction(action: MobileBottomControlAction | undefined, fallback: boolean): boolean {
  if (!action) return false;
  return action.grow ?? fallback;
}

export function MobileBottomControl({
  bottomOffset = 12,
  leftAction,
  rightAction,
}: MobileBottomControlProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const renderAction = (action: MobileBottomControlAction | undefined, fallbackGrow: boolean) => {
    if (!action) return null;

    const Icon = action.icon;
    const variant = action.variant ?? 'filled';
    const shouldGrow = isGrowingAction(action, fallbackGrow);

    if (variant === 'filled') {
      return (
        <Button
          key={action.label}
          radius="xl"
          size="md"
          variant="filled"
          color="teal"
          disabled={action.disabled}
          onClick={action.onClick}
          leftSection={Icon ? <Icon size={18} /> : undefined}
          style={{ flex: shouldGrow ? '1 1 0' : '0 0 auto' }}
        >
          {action.label}
        </Button>
      );
    }

    return (
      <UnstyledButton
        key={action.label}
        onClick={action.onClick}
        disabled={action.disabled}
        style={{
          flex: shouldGrow ? '1 1 0' : '0 0 auto',
          minWidth: shouldGrow ? undefined : 112,
          borderRadius: 18,
          padding: leftAction ? '12px 16px' : '14px 18px',
          background: isDark
            ? `linear-gradient(135deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[6]} 100%)`
            : 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          color: '#ffffff',
          boxShadow: isDark ? '0 14px 30px rgba(0, 0, 0, 0.34)' : '0 14px 30px rgba(15, 23, 42, 0.22)',
          opacity: action.disabled ? 0.55 : 1,
        }}
      >
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Group gap="xs" wrap="nowrap">
            {Icon && <Icon size={18} />}
            <div>
              <Text fw={700} size="sm">{action.label}</Text>
              {!leftAction && action.description && (
                <Text size="xs" c="rgba(255,255,255,0.68)">
                  {action.description}
                </Text>
              )}
            </div>
          </Group>
          {action.rightSection}
        </Group>
      </UnstyledButton>
    );
  };

  if (!leftAction && !rightAction) return null;

  return (
    <Portal>
      <Group
        className="mobile-bottom-control"
        wrap="nowrap"
        gap="xs"
        style={{
          position: 'fixed',
          left: 'calc(12px + var(--safe-area-left))',
          right: 'calc(12px + var(--safe-area-right))',
          bottom: `calc(${bottomOffset}px + var(--safe-area-bottom))`,
          zIndex: 44,
          padding: 8,
          borderRadius: 24,
          background: isDark ? 'rgba(30, 41, 59, 0.94)' : 'rgba(255,255,255,0.94)',
          backdropFilter: 'blur(16px)',
          border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(148,163,184,0.22)',
          boxShadow: isDark ? '0 18px 42px rgba(0, 0, 0, 0.34)' : '0 18px 42px rgba(15, 23, 42, 0.18)',
        }}
      >
        {renderAction(leftAction, true)}
        {renderAction(rightAction, !isFilledAction(leftAction))}
      </Group>
    </Portal>
  );
}
