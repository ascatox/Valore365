import { useEffect, useRef, useState } from 'react';

// A swipe is a quick, mostly horizontal drag: longer than this, at least
// this many times wider than tall, and within this time.
const MIN_DISTANCE_PX = 60;
const MIN_HORIZONTAL_RATIO = 1.5;
const MAX_DURATION_MS = 700;

// Gestures that start on these keep their own horizontal behaviour:
// scrolling rows, charts (touch scrub), sliders, inputs and anything
// opted out with data-no-swipe.
const IGNORED_TARGETS = [
  '[data-no-swipe]',
  '.recharts-wrapper',
  'input',
  'textarea',
  'select',
  '[role="slider"]',
  '.mantine-Tabs-list',
  '.mantine-SegmentedControl-root',
].join(',');

function startsInHorizontalScroller(target: Element, boundary: Element): boolean {
  let el: Element | null = target;
  while (el && el !== boundary) {
    if (el.scrollWidth > el.clientWidth + 1) {
      const overflowX = window.getComputedStyle(el).overflowX;
      if (overflowX === 'auto' || overflowX === 'scroll') return true;
    }
    el = el.parentElement;
  }
  return false;
}

interface UseSwipeTabsOptions {
  tabs: readonly string[];
  active: string | null;
  onChange: (tab: string) => void;
  enabled?: boolean;
}

/**
 * Switch between tabs with a horizontal swipe on the element given the
 * returned callback ref: swipe left for the next tab, right for the previous.
 */
export function useSwipeTabs<T extends HTMLElement = HTMLDivElement>({ tabs, active, onChange, enabled = true }: UseSwipeTabsOptions) {
  // State, not a ref, so the listeners attach when the element mounts later.
  const [node, setNode] = useState<T | null>(null);
  // Latest values without re-binding the listeners on every render.
  const stateRef = useRef({ tabs, active, onChange });
  stateRef.current = { tabs, active, onChange };

  useEffect(() => {
    if (!enabled || !node) return;

    let start: { x: number; y: number; t: number } | null = null;

    const handleStart = (event: TouchEvent) => {
      const target = event.target as Element | null;
      if (
        event.touches.length !== 1
        || !target
        || target.closest(IGNORED_TARGETS)
        || startsInHorizontalScroller(target, node)
      ) {
        start = null;
        return;
      }
      const touch = event.touches[0];
      // event.timeStamp is when the finger moved, not when this handler ran:
      // a busy main thread (a tab still rendering) must not void the swipe.
      start = { x: touch.clientX, y: touch.clientY, t: event.timeStamp };
    };

    const handleEnd = (event: TouchEvent) => {
      if (!start) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      const elapsed = event.timeStamp - start.t;
      start = null;
      if (
        Math.abs(dx) < MIN_DISTANCE_PX
        || Math.abs(dx) < Math.abs(dy) * MIN_HORIZONTAL_RATIO
        || elapsed > MAX_DURATION_MS
      ) {
        return;
      }
      const { tabs: list, active: current, onChange: change } = stateRef.current;
      const index = current ? list.indexOf(current) : -1;
      if (index === -1) return;
      const next = dx < 0 ? index + 1 : index - 1;
      if (next < 0 || next >= list.length) return;
      change(list[next]);
      // Bring the newly active tab into view in a scrolling tab row, moving
      // the row only (scrollIntoView would also scroll the page vertically).
      window.requestAnimationFrame(() => {
        document.querySelectorAll('[role="tab"][aria-selected="true"]').forEach((tab) => {
          const row = tab.closest('.mantine-Tabs-list');
          if (!row) return;
          const tabBox = tab.getBoundingClientRect();
          const rowBox = row.getBoundingClientRect();
          if (tabBox.left < rowBox.left) {
            row.scrollBy({ left: tabBox.left - rowBox.left - 8, behavior: 'smooth' });
          } else if (tabBox.right > rowBox.right) {
            row.scrollBy({ left: tabBox.right - rowBox.right + 8, behavior: 'smooth' });
          }
        });
      });
    };

    const handleCancel = () => { start = null; };

    node.addEventListener('touchstart', handleStart, { passive: true });
    node.addEventListener('touchend', handleEnd, { passive: true });
    node.addEventListener('touchcancel', handleCancel, { passive: true });
    return () => {
      node.removeEventListener('touchstart', handleStart);
      node.removeEventListener('touchend', handleEnd);
      node.removeEventListener('touchcancel', handleCancel);
    };
  }, [enabled, node]);

  return setNode;
}
