import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { useSwipeTabs } from './useSwipeTabs';

const TABS = ['a', 'b', 'c'];

function Harness({ active, onChange }: { active: string; onChange: (tab: string) => void }) {
  const ref = useSwipeTabs({ tabs: TABS, active, onChange });
  return (
    <div ref={ref} data-testid="area">
      <span data-testid="content">contenuto</span>
      <div data-no-swipe data-testid="excluded">carosello</div>
    </div>
  );
}

function swipe(target: Element, dx: number, dy = 0) {
  fireEvent.touchStart(target, { touches: [{ clientX: 200, clientY: 300 }] });
  fireEvent.touchEnd(target, { changedTouches: [{ clientX: 200 + dx, clientY: 300 + dy }] });
}

describe('useSwipeTabs', () => {
  it('moves to the next tab on a left swipe and the previous on a right swipe', () => {
    const onChange = vi.fn();
    render(<Harness active="b" onChange={onChange} />);
    swipe(screen.getByTestId('content'), -120);
    expect(onChange).toHaveBeenLastCalledWith('c');
    swipe(screen.getByTestId('content'), 120);
    expect(onChange).toHaveBeenLastCalledWith('a');
  });

  it('stops at the first and last tab', () => {
    const onChange = vi.fn();
    render(<Harness active="a" onChange={onChange} />);
    swipe(screen.getByTestId('content'), 120);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('ignores short or mostly vertical drags', () => {
    const onChange = vi.fn();
    render(<Harness active="b" onChange={onChange} />);
    swipe(screen.getByTestId('content'), -30);
    swipe(screen.getByTestId('content'), -90, 120);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('leaves gestures that start in an excluded area alone', () => {
    const onChange = vi.fn();
    render(<Harness active="b" onChange={onChange} />);
    swipe(screen.getByTestId('excluded'), -120);
    expect(onChange).not.toHaveBeenCalled();
  });
});
