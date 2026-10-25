import { Group, Portal, Text, UnstyledButton, alpha, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { Fragment, useRef, type CSSProperties, type PointerEvent } from 'react';

type NavIcon = React.ComponentType<{ size?: string | number; className?: string; style?: CSSProperties }>;

interface MobileBottomNavItem {
  value: string;
  label: string;
  icon: NavIcon;
  disabled?: boolean;
}

interface MobileBottomNavCenterAction {
  label: string;
  icon: NavIcon;
  onClick: () => void;
}

// Press key of the center action, distinct from any item value.
const CENTER_ACTION_KEY = '__center-action__';

// A tap that moves less than this is a tap, not a drag.
const TAP_SLOP_PX = 10;
// Clicks following a pointer-activated tap within this window are duplicates.
const CLICK_DEDUPE_MS = 500;

interface MobileBottomNavProps {
  items: MobileBottomNavItem[];
  value: string | null;
  onChange: (value: string) => void;
  bottomOffset?: number;
  /** Raised primary button placed in the middle of the items (e.g. "+"). */
  centerAction?: MobileBottomNavCenterAction;
}

export function MobileBottomNav({ items, value, onChange, bottomOffset = 12, centerAction }: MobileBottomNavProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const pressRef = useRef<{ value: string; x: number; y: number } | null>(null);
  const lastPointerTapRef = useRef(0);

  // iOS drops the synthetic click when a tap lands while the page is still
  // momentum-scrolling, so a tab needed two taps. Activate on pointerup and
  // keep onClick for keyboard/assistive activation, de-duplicated.
  const handlePointerDown = (event: PointerEvent, itemValue: string) => {
    pressRef.current = { value: itemValue, x: event.clientX, y: event.clientY };
  };

  const handlePointerUp = (event: PointerEvent, itemValue: string, activate: () => void = () => onChange(itemValue)) => {
    const press = pressRef.current;
    pressRef.current = null;
    if (
      !press
      || press.value !== itemValue
      || Math.abs(event.clientX - press.x) > TAP_SLOP_PX
      || Math.abs(event.clientY - press.y) > TAP_SLOP_PX
    ) {
      return;
    }
    lastPointerTapRef.current = Date.now();
    activate();
  };

  const handleClick = (itemValue: string, activate: () => void = () => onChange(itemValue)) => {
    if (Date.now() - lastPointerTapRef.current < CLICK_DEDUPE_MS) return;
    activate();
  };

  if (items.length === 0) return null;

  return (
    <Portal>
    <Group
      className="mobile-bottom-nav"
      justify="space-between"
      wrap="nowrap"
      gap={6}
      style={{
        position: 'fixed',
        left: 'calc(12px + var(--safe-area-left))',
        right: 'calc(12px + var(--safe-area-right))',
        bottom: `calc(${bottomOffset}px + var(--safe-area-bottom-floating))`,
        zIndex: 45,
        touchAction: 'none',
        padding: 6,
        borderRadius: 20,
        background: isDark ? alpha(theme.colors.dark[5], 0.94) : 'rgba(255,255,255,0.94)',
        backdropFilter: 'blur(16px)',
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(148,163,184,0.22)',
        boxShadow: isDark ? '0 18px 42px rgba(0, 0, 0, 0.34)' : '0 18px 42px rgba(15, 23, 42, 0.18)',
      }}
    >
      {items.map((item, index) => {
        const Icon = item.icon;
        const isActive = value === item.value;
        const CenterIcon = centerAction?.icon;
        return (
          <Fragment key={item.value}>
          {centerAction && CenterIcon && index === Math.ceil(items.length / 2) && (
            <UnstyledButton
              // Same pointer activation as the tabs, so a tap during momentum
              // scrolling still opens the sheet on iOS.
              onPointerDown={(event) => handlePointerDown(event, CENTER_ACTION_KEY)}
              onPointerUp={(event) => handlePointerUp(event, CENTER_ACTION_KEY, centerAction.onClick)}
              onPointerCancel={() => { pressRef.current = null; }}
              onClick={() => handleClick(CENTER_ACTION_KEY, centerAction.onClick)}
              aria-label={centerAction.label}
              style={{
                flex: '0 0 auto',
                width: 48,
                height: 48,
                margin: '0 4px',
                borderRadius: 16,
                display: 'grid',
                placeItems: 'center',
                background: 'var(--mantine-primary-color-filled)',
                color: '#ffffff',
                boxShadow: '0 8px 18px rgba(15, 118, 110, 0.35)',
              }}
            >
              <CenterIcon size={24} />
            </UnstyledButton>
          )}
          <UnstyledButton
            disabled={item.disabled}
            onPointerDown={item.disabled ? undefined : (event) => handlePointerDown(event, item.value)}
            onPointerUp={item.disabled ? undefined : (event) => handlePointerUp(event, item.value)}
            onPointerCancel={() => { pressRef.current = null; }}
            onClick={item.disabled ? undefined : () => handleClick(item.value)}
            style={{
              flex: '1 1 0',
              minWidth: 44,
              minHeight: 44,
              borderRadius: 16,
              padding: '10px 4px',
              background: isActive ? 'linear-gradient(135deg, #0f766e 0%, #134e4a 100%)' : 'transparent',
              color: isActive ? '#ffffff' : (isDark ? theme.colors.gray[3] : '#475569'),
              textAlign: 'center',
              opacity: item.disabled ? 0.4 : 1,
              transition: 'all 140ms ease',
            }}
          >
            <Icon size={20} className="nav-icon" style={{ margin: '0 auto 3px auto', display: 'block' }} />
            <Text size="xs" className="nav-label" fw={700} truncate="end" style={{ lineHeight: 1.1 }}>
              {item.label}
            </Text>
          </UnstyledButton>
          </Fragment>
        );
      })}
    </Group>
    </Portal>
  );
}
