import { MantineProvider, Tabs } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { getColorTheme, type ColorThemeId } from './colorTheme';
import { buildTheme } from './mantineTheme';

function renderTabs(themeId: ColorThemeId, variant?: 'default' | 'pills') {
  render(
    <MantineProvider theme={buildTheme(getColorTheme(themeId))} forceColorScheme="light">
      <Tabs defaultValue="one" variant={variant} data-testid="tabs">
        <Tabs.List>
          <Tabs.Tab value="one">Uno</Tabs.Tab>
          <Tabs.Tab value="two">Due</Tabs.Tab>
        </Tabs.List>
      </Tabs>
    </MantineProvider>,
  );
  return {
    root: screen.getByTestId('tabs'),
    active: screen.getByRole('tab', { name: 'Uno' }),
    inactive: screen.getByRole('tab', { name: 'Due' }),
  };
}

// Mantine's generated colour variables (its <style> tags).
const mantineCss = () => [...document.querySelectorAll('style')].map((style) => style.textContent).join('\n');

describe('navigation accent in the Mantine theme', () => {
  it('registers the accent tuple as a Mantine colour', () => {
    const christmas = getColorTheme('christmas');
    expect(buildTheme(christmas).colors?.accent).toEqual(christmas.accent);
    expect(buildTheme(christmas).colors?.teal).toEqual(christmas.primary);
    const petrol = getColorTheme('petrol');
    expect(buildTheme(petrol).colors?.accent).toEqual(petrol.primary);
  });

  it('colours the active tab indicator and label in Christmas red under Natale', () => {
    const { root, active, inactive } = renderTabs('christmas');
    expect(root.style.getPropertyValue('--tabs-color')).toBe('var(--mantine-color-accent-filled)');
    expect(active).toHaveAttribute('data-active');
    // index.css gives .v365-accent-tab[data-active] the accent text colour.
    expect(active).toHaveClass('v365-accent-tab');
    expect(inactive).not.toHaveAttribute('data-active');
    const css = mantineCss();
    expect(css).toContain(`--mantine-color-accent-6: ${getColorTheme('christmas').accent[6]}`);
    expect(css).toContain(`--mantine-color-accent-4: ${getColorTheme('christmas').accent[4]}`);
  });

  it('fills the active pill with the accent under Natale', () => {
    const { root, active } = renderTabs('christmas', 'pills');
    expect(root.style.getPropertyValue('--tabs-color')).toBe('var(--mantine-color-accent-filled)');
    // Pills keep white text: the label rule skips them.
    expect(active).toHaveAttribute('data-variant', 'pills');
  });

  it('keeps other themes on the brand colour, with no accent label class', () => {
    const { root, active } = renderTabs('petrol');
    // accent = petrol's brand tuple, so the indicator keeps today's colour.
    expect(root.style.getPropertyValue('--tabs-color')).toBe('var(--mantine-color-accent-filled)');
    expect(active).not.toHaveClass('v365-accent-tab');
    expect(mantineCss()).toContain(`--mantine-color-accent-6: ${getColorTheme('petrol').primary[6]}`);
  });
});
