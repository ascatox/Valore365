import { useEffect, useRef, useState, useCallback } from 'react';

const THRESHOLD = 80;
const MAX_PULL = 120;

export function usePullToRefresh(onRefresh: () => void) {
  const [pulling, setPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const startY = useRef(0);
  const isPulling = useRef(false);

  const handleRefresh = useCallback(() => {
    onRefresh();
  }, [onRefresh]);

  useEffect(() => {
    const onTouchStart = (e: TouchEvent) => {
      if (window.scrollY === 0) {
        startY.current = e.touches[0].clientY;
        isPulling.current = true;
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!isPulling.current) return;
      const dy = e.touches[0].clientY - startY.current;
      if (dy > 0) {
        const distance = Math.min(dy, MAX_PULL);
        setPullDistance(distance);
        setPulling(true);
        if (dy > 10) e.preventDefault();
      } else {
        isPulling.current = false;
        setPulling(false);
        setPullDistance(0);
      }
    };

    const onTouchEnd = () => {
      if (isPulling.current && pullDistance >= THRESHOLD) {
        handleRefresh();
      }
      isPulling.current = false;
      setPulling(false);
      setPullDistance(0);
    };

    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', onTouchEnd, { passive: true });

    return () => {
      document.removeEventListener('touchstart', onTouchStart);
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('touchend', onTouchEnd);
    };
  }, [pullDistance, handleRefresh]);

  return { pulling, pullDistance, reached: pullDistance >= THRESHOLD };
}
