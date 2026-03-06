import { Group, Text, UnstyledButton } from '@mantine/core';
import type { TablerIconsProps } from '@tabler/icons-react';

interface MobileBottomNavItem {
  value: string;
  label: string;
  icon: React.ComponentType<TablerIconsProps>;
}

interface MobileBottomNavProps {
  items: MobileBottomNavItem[];
  value: string | null;
  onChange: (value: string) => void;
}

export function MobileBottomNav({ items, value, onChange }: MobileBottomNavProps) {
  return (
    <Group
      justify="space-between"
      wrap="nowrap"
      gap={6}
      style={{
        position: 'fixed',
        left: 12,
        right: 12,
        bottom: 12,
        zIndex: 45,
        padding: 8,
        borderRadius: 24,
        background: 'rgba(255,255,255,0.94)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(148,163,184,0.22)',
        boxShadow: '0 18px 42px rgba(15, 23, 42, 0.18)',
      }}
    >
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = value === item.value;
        return (
          <UnstyledButton
            key={item.value}
            onClick={() => onChange(item.value)}
            style={{
              flex: '1 1 0',
              minWidth: 0,
              borderRadius: 18,
              padding: '10px 6px',
              background: isActive ? 'linear-gradient(135deg, #0f766e 0%, #134e4a 100%)' : 'transparent',
              color: isActive ? '#ffffff' : '#475569',
              textAlign: 'center',
              transition: 'all 140ms ease',
            }}
          >
            <Icon size={18} style={{ margin: '0 auto 4px auto', display: 'block' }} />
            <Text size="xs" fw={700} truncate="end">
              {item.label}
            </Text>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}
