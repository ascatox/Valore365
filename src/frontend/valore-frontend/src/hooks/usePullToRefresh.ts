import { useEffect, useRef, useState } from 'react';

const THRESHOLD = 72;
const MAX_PULL = 104;
const MOBILE_QUERY = '(max-width: 48em)';
const INTERACTIVE_SELECTOR = 'input, textarea, select, button, a, [contenteditable="true"], [role="dialog"]';

interface PullToRefreshOptions {
  enabled?: boolean;
}

function hasScrollableParent(target: HTMLElement | null, boundary: HTMLElement): boolean {
  let node = target?.parentElement ?? null;

  while (node && node !== boundary && node !== document.body) {
    const style = window.getComputedStyle(node);
    const isScrollable = /(auto|scroll|overlay)/.test(style.overflowY);

    if (isScrollable && node.scrollHeight > node.clientHeight) {
      return true;
    }

    node = node.parentElement;
  }

  return false;
}

export function usePullToRefresh(
  targetRef: React.RefObject<HTMLElement | null>,
  onRefresh: () => void,
  options: PullToRefreshOptions = {},
) {
  const { enabled = true } = options;
  const [pulling, setPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const startYRef = useRef(0);
  const trackingRef = useRef(false);
  const pullDistanceRef = useRef(0);
  const onRefreshRef = useRef(onRefresh);

  onRefreshRef.current = onRefresh;

  useEffect(() => {
    const root = targetRef.current;
    const isMobile = window.matchMedia(MOBILE_QUERY).matches;

    if (!enabled || !root || !isMobile) {
      trackingRef.current = false;
      pullDistanceRef.current = 0;
      setPulling(false);
      setPullDistance(0);
      return;
    }

    const reset = () => {
      trackingRef.current = false;
      pullDistanceRef.current = 0;
      setPulling(false);
      setPullDistance(0);
    };

    const onTouchStart = (event: TouchEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;

      if (event.touches.length !== 1 || window.scrollY > 0 || !target) {
        reset();
        return;
      }

      if (target.closest(INTERACTIVE_SELECTOR) || hasScrollableParent(target, root)) {
        reset();
        return;
      }

      startYRef.current = event.touches[0].clientY;
      trackingRef.current = true;
    };

    const onTouchMove = (event: TouchEvent) => {
      if (!trackingRef.current) {
        return;
      }

      const dy = event.touches[0].clientY - startYRef.current;

      if (window.scrollY > 0 || dy <= 0) {
        reset();
        return;
      }

      const dampenedDistance = Math.min(MAX_PULL, dy * 0.55);
      pullDistanceRef.current = dampenedDistance;
      setPulling(true);
      setPullDistance(dampenedDistance);

      if (dy > 14) {
        event.preventDefault();
      }
    };

    const onTouchEnd = () => {
      if (trackingRef.current && pullDistanceRef.current >= THRESHOLD) {
        onRefreshRef.current();
      }

      reset();
    };

    root.addEventListener('touchstart', onTouchStart, { passive: true });
    root.addEventListener('touchmove', onTouchMove, { passive: false });
    root.addEventListener('touchend', onTouchEnd, { passive: true });
    root.addEventListener('touchcancel', onTouchEnd, { passive: true });

    return () => {
      root.removeEventListener('touchstart', onTouchStart);
      root.removeEventListener('touchmove', onTouchMove);
      root.removeEventListener('touchend', onTouchEnd);
      root.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [enabled, targetRef]);

  return { pulling, pullDistance, reached: pullDistance >= THRESHOLD };
}
