import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { MobileBottomNav } from './MobileBottomNav';

const Icon = () => null;
const items = [
  { value: 'panoramica', label: 'Home', icon: Icon },
  { value: 'posizioni', label: 'Posizioni', icon: Icon },
];

function renderNav(onChange = vi.fn()) {
  render(
    <MantineProvider>
      <MobileBottomNav items={items} value="posizioni" onChange={onChange} />
    </MantineProvider>,
  );
  return { onChange, home: screen.getByText('Home').closest('button')! };
}

describe('MobileBottomNav', () => {
  it('activates on pointerup even when no click follows (iOS momentum scroll)', () => {
    const { onChange, home } = renderNav();
    fireEvent.pointerDown(home, { clientX: 20, clientY: 20 });
    fireEvent.pointerUp(home, { clientX: 22, clientY: 21 });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('panoramica');
  });

  it('does not fire twice when the click follows the pointerup', () => {
    const { onChange, home } = renderNav();
    fireEvent.pointerDown(home, { clientX: 20, clientY: 20 });
    fireEvent.pointerUp(home, { clientX: 20, clientY: 20 });
    fireEvent.click(home);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('ignores drags', () => {
    const { onChange, home } = renderNav();
    fireEvent.pointerDown(home, { clientX: 20, clientY: 20 });
    fireEvent.pointerUp(home, { clientX: 20, clientY: 60 });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('still activates on a plain click (keyboard / assistive tech)', () => {
    const { onChange, home } = renderNav();
    fireEvent.click(home);
    expect(onChange).toHaveBeenCalledWith('panoramica');
  });
});
