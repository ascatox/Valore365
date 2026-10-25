import { useRef, type ReactNode, type TouchEvent } from 'react';
import { Box, Drawer, Text } from '@mantine/core';

interface BottomSheetProps {
  opened: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
}

// Dragging the top of the sheet down by more than this closes it.
const CLOSE_DISTANCE_PX = 80;

/**
 * Panel that rises from the bottom and sizes to its content. It has a grab
 * handle instead of a close button: drag the top down, tap outside or press
 * Escape to close it.
 */
export function BottomSheet({ opened, onClose, title, children }: BottomSheetProps) {
  const contentRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ startY: number; dy: number } | null>(null);

  const setOffset = (dy: number, animate: boolean) => {
    const el = contentRef.current;
    if (!el) return;
    el.style.transition = animate ? 'transform 180ms ease' : 'none';
    el.style.transform = dy > 0 ? `translateY(${dy}px)` : '';
  };

  const handleTouchStart = (event: TouchEvent) => {
    dragRef.current = { startY: event.touches[0].clientY, dy: 0 };
  };

  const handleTouchMove = (event: TouchEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    drag.dy = Math.max(0, event.touches[0].clientY - drag.startY);
    setOffset(drag.dy, false);
  };

  const handleTouchEnd = () => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;
    if (drag.dy > CLOSE_DISTANCE_PX) {
      onClose();
      // Reset after Mantine's closing transition has taken the sheet away.
      window.setTimeout(() => setOffset(0, false), 300);
    } else {
      setOffset(0, true);
    }
  };

  return (
    <Drawer.Root opened={opened} onClose={onClose} position="bottom">
      <Drawer.Overlay />
      <Drawer.Content
        ref={contentRef}
        style={{
          height: 'auto',
          width: '100%',
          flex: '0 0 auto',
          maxHeight: '90dvh',
          borderRadius: '20px 20px 0 0',
        }}
      >
        <Box
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onTouchCancel={handleTouchEnd}
          style={{ touchAction: 'none', position: 'sticky', top: 0, zIndex: 1, background: 'var(--mantine-color-body)' }}
        >
          <Box
            aria-hidden
            style={{
              width: 40,
              height: 5,
              borderRadius: 3,
              margin: '8px auto 0',
              background: 'var(--mantine-color-default-border)',
            }}
          />
          {title ? (
            <Text fw={700} size="lg" px="md" pt="sm" pb="xs" c="var(--mantine-primary-color-filled)">
              {title}
            </Text>
          ) : (
            <Box h={12} />
          )}
        </Box>
        <Drawer.Body style={{ paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' }}>
          {children}
        </Drawer.Body>
      </Drawer.Content>
    </Drawer.Root>
  );
}
