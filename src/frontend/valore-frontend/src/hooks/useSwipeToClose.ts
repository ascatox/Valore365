import { useCallback, useRef } from 'react';

interface SwipeToCloseOptions {
  /** Minimum downward distance in px to trigger close (default 80) */
  threshold?: number;
  /** Max starting Y position from the top of the element (default 120) */
  maxStartY?: number;
  /** Whether the gesture is enabled (default true) */
  enabled?: boolean;
}

interface SwipeToCloseHandlers {
  onTouchStart: (e: React.TouchEvent) => void;
  onTouchEnd: (e: React.TouchEvent) => void;
}

/**
 * Provides swipe-down-to-close gesture handlers for drawers and modals.
 * Swipe must start from the top area of the element and travel at least
 * `threshold` pixels downward to trigger `onClose`.
 */
export function useSwipeToClose(
  onClose: () => void,
  options: SwipeToCloseOptions = {},
): SwipeToCloseHandlers {
  const { threshold = 80, maxStartY = 120, enabled = true } = options;
  const touchStartY = useRef<number | null>(null);

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled) return;
      touchStartY.current = e.touches[0].clientY;
    },
    [enabled],
  );

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled || touchStartY.current === null) return;
      const diff = e.changedTouches[0].clientY - touchStartY.current;
      if (diff > threshold && touchStartY.current < maxStartY) {
        onClose();
      }
      touchStartY.current = null;
    },
    [enabled, threshold, maxStartY, onClose],
  );

  return { onTouchStart, onTouchEnd };
}
