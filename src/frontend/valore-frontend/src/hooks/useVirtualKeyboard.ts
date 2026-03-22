import { useEffect, useState } from 'react';

/**
 * Detects whether the iOS/Android virtual keyboard is open by comparing
 * the visual viewport height to the window inner height.
 */
export function useVirtualKeyboard(enabled = true): boolean {
  const [keyboardOpen, setKeyboardOpen] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setKeyboardOpen(false);
      return;
    }

    const vv = window.visualViewport;
    if (!vv) return;

    const onResize = () => {
      setKeyboardOpen(vv.height < window.innerHeight * 0.75);
    };

    vv.addEventListener('resize', onResize);
    onResize();
    return () => vv.removeEventListener('resize', onResize);
  }, [enabled]);

  return keyboardOpen;
}
