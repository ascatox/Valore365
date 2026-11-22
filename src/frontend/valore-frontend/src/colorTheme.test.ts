import indexHtml from '../index.html?raw';
import {
  COLOR_THEMES,
  COLOR_THEME_ATTRIBUTE,
  COLOR_THEME_STORAGE_KEY,
  DEFAULT_COLOR_THEME,
  applyColorTheme,
  getActiveColorTheme,
  getColorTheme,
  getColorThemePreference,
  setColorThemePreference,
} from './colorTheme';

const MOBILE_QUERY = '(max-width: 48em)';
const originalMatchMedia = window.matchMedia;

function setViewport(phone: boolean) {
  window.matchMedia = ((query: string) => ({
    ...originalMatchMedia(query),
    matches: phone && query === MOBILE_QUERY,
  })) as typeof window.matchMedia;
}

const activeAttribute = () => document.documentElement.getAttribute(COLOR_THEME_ATTRIBUTE);

// WCAG 2 contrast ratio between two #rrggbb colours.
function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

describe('colour themes', () => {
  it('offers the default and at least five more, each with a label', () => {
    expect(COLOR_THEMES.length).toBeGreaterThanOrEqual(6);
    expect(COLOR_THEMES[0].id).toBe(DEFAULT_COLOR_THEME);
    expect(new Set(COLOR_THEMES.map((theme) => theme.id)).size).toBe(COLOR_THEMES.length);
    COLOR_THEMES.forEach((theme) => expect(theme.label).not.toBe(''));
  });

  it.each(COLOR_THEMES)('$id has ten valid hex shades per tuple', (theme) => {
    [theme.primary, theme.accent, theme.dark].forEach((tuple) => {
      expect(tuple).toHaveLength(10);
      tuple.forEach((shade) => expect(shade).toMatch(/^#[0-9a-f]{6}$/));
    });
    [theme.lightPageBg, ...theme.swatch, ...theme.swatchDark].forEach((color) => expect(color).toMatch(/^#[0-9a-f]{6}$/));
  });

  it.each(COLOR_THEMES)('$id keeps text readable in light and dark', (theme) => {
    expect(contrast('#ffffff', theme.primary[6])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[6], theme.lightPageBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[4], theme.dark[6])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(theme.primary[4], theme.dark[7])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(COLOR_THEMES)('$id maps onto the same shade roles as petrol', (theme) => {
    // Both tuples go from light to dark like petrol's, so every role
    // (shade 6 fill, shade 4 dark-mode text, dark[7] page, dark[6] cards,
    // dark[4] borders) lands on a comparable tone.
    [theme.primary, theme.dark].forEach((tuple) => {
      for (let i = 1; i < tuple.length; i += 1) {
        expect(luminance(tuple[i])).toBeLessThan(luminance(tuple[i - 1]));
      }
    });
    // Filled gradients (shade 6 to 8) keep white text readable.
    expect(contrast('#ffffff', theme.primary[8])).toBeGreaterThanOrEqual(4.5);
    // Light page near white; dark surfaces stacked page < cards < borders.
    expect(luminance(theme.lightPageBg)).toBeGreaterThan(0.85);
    expect(luminance(theme.dark[7])).toBeLessThan(luminance(theme.dark[6]));
    expect(luminance(theme.dark[6])).toBeLessThan(luminance(theme.dark[4]));
  });

  it('uses the brand tuple as accent in every theme but Natale, so their UI is unchanged', () => {
    COLOR_THEMES.filter((theme) => theme.id !== 'christmas').forEach((theme) => {
      expect(theme.hasOwnAccent).toBe(false);
      expect(theme.accent).toEqual(theme.primary);
    });
  });

  it('keeps the default theme on the petrol colours', () => {
    const petrol = getColorTheme('petrol');
    expect(petrol.primary[6]).toBe('#0f766e');
    expect(petrol.dark[7]).toBe('#0e1514');
    expect(petrol.lightPageBg).toBe('#f5f7f7');
  });

  it('computes the swatch from the brand tuple, lighter tone first on dark', () => {
    COLOR_THEMES.filter((theme) => theme.id !== 'christmas').forEach((theme) => {
      expect(theme.swatch).toEqual([theme.primary[6], theme.primary[3]]);
      expect(theme.swatchDark).toEqual([theme.primary[3], theme.primary[6]]);
    });
  });

  describe('Natale', () => {
    const christmas = getColorTheme('christmas');
    // Gain tuple from mantineTheme.tsx (shade 6 light text/fill, shade 4 dark text).
    const gain = { light: '#15803d', dark: '#4ade80' };
    const hue = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
      const max = Math.max(r, g, b);
      const delta = max - Math.min(r, g, b);
      const h = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
      return (h * 60 + 360) % 360;
    };

    it('is the last theme, labelled Natale', () => {
      expect(COLOR_THEMES[COLOR_THEMES.length - 1]).toBe(christmas);
      expect(christmas.label).toBe('Natale');
    });

    it('uses a bluish pine green that is not the gain green', () => {
      // Pine leans towards blue (hue past 150°) where the gain green sits at ~142°.
      [christmas.primary[6], christmas.primary[4]].forEach((shade) => {
        expect(hue(shade)).toBeGreaterThan(150);
        expect(hue(shade)).toBeLessThan(165);
      });
      expect(hue(gain.light)).toBeLessThan(145);
      expect(christmas.primary[6]).not.toBe(gain.light);
      expect(christmas.primary[4]).not.toBe(gain.dark);
    });

    it('has a Christmas red accent with the same contrast roles as the brand', () => {
      const { accent } = christmas;
      expect(christmas.hasOwnAccent).toBe(true);
      expect(accent).not.toEqual(christmas.primary);
      // Light to dark like the brand tuple.
      for (let i = 1; i < accent.length; i += 1) {
        expect(luminance(accent[i])).toBeLessThan(luminance(accent[i - 1]));
      }
      // Shade 6: label on white cards and on the light page; white on it (pills, nav fill).
      expect(contrast(accent[6], '#ffffff')).toBeGreaterThanOrEqual(4.5);
      expect(contrast(accent[6], christmas.lightPageBg)).toBeGreaterThanOrEqual(4.5);
      // Shade 4: label on dark cards and on the dark page.
      expect(contrast(accent[4], christmas.dark[6])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(accent[4], christmas.dark[7])).toBeGreaterThanOrEqual(4.5);
      // Gradient end of the active bottom-nav item keeps white readable.
      expect(contrast('#ffffff', accent[8])).toBeGreaterThanOrEqual(4.5);
      expect(contrast('#ffffff', accent[9])).toBeGreaterThanOrEqual(4.5);
    });

    it('uses a cranberry red that is not the loss red', () => {
      // Loss tuple from mantineTheme.tsx sits at hue ~5°; the accent leans to blue (past 340°).
      const loss = { light: '#b42318', dark: '#f87171' };
      [christmas.accent[6], christmas.accent[4]].forEach((shade) => {
        expect(hue(shade)).toBeGreaterThan(340);
        expect(hue(shade)).toBeLessThan(358);
      });
      expect(hue(loss.light)).toBeLessThan(10);
      expect(christmas.accent[6]).not.toBe(loss.light);
      expect(christmas.accent[4]).not.toBe(loss.dark);
    });

    it('shows pine green and Christmas red in the picker, in light and dark', () => {
      expect(christmas.swatch).toEqual([christmas.primary[6], christmas.accent[6]]);
      expect(christmas.swatchDark).toEqual([christmas.primary[4], christmas.accent[4]]);
      // The check mark (white on light cards, dark[7] on dark ones) sits on the main tone.
      expect(contrast('#ffffff', christmas.swatch[0])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(christmas.dark[7], christmas.swatchDark[0])).toBeGreaterThanOrEqual(4.5);
    });
  });
});

describe('colour theme preference', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    setColorThemePreference(DEFAULT_COLOR_THEME);
  });

  it('starts on the default theme', () => {
    setViewport(true);
    applyColorTheme();
    expect(getColorThemePreference()).toBe('petrol');
    expect(getActiveColorTheme().id).toBe('petrol');
    expect(activeAttribute()).toBe('petrol');
  });

  it('applies the chosen theme on a phone and remembers it', () => {
    setViewport(true);
    setColorThemePreference('ocean');
    expect(getColorThemePreference()).toBe('ocean');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBe('ocean');
    expect(getActiveColorTheme().id).toBe('ocean');
    expect(activeAttribute()).toBe('ocean');
  });

  it('goes back to the default without leaving a stored value', () => {
    setViewport(true);
    setColorThemePreference('bronze');
    setColorThemePreference('petrol');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBeNull();
    expect(activeAttribute()).toBe('petrol');
  });

  it('ignores an unknown stored value', () => {
    setViewport(true);
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'fucsia');
    applyColorTheme();
    expect(getColorThemePreference()).toBe('petrol');
    expect(getActiveColorTheme().id).toBe('petrol');
    expect(activeAttribute()).toBe('petrol');
  });

  it('applies the chosen theme on desktop and tablet viewports too', () => {
    setViewport(false);
    setColorThemePreference('amethyst');
    expect(getColorThemePreference()).toBe('amethyst');
    expect(getActiveColorTheme().id).toBe('amethyst');
    expect(activeAttribute()).toBe('amethyst');
  });

  it('keeps the chosen theme across the phone breakpoint', () => {
    setViewport(false);
    setColorThemePreference('graphite');
    expect(getActiveColorTheme().id).toBe('graphite');
    setViewport(true);
    applyColorTheme();
    expect(getActiveColorTheme().id).toBe('graphite');
    setViewport(false);
    applyColorTheme();
    expect(getActiveColorTheme().id).toBe('graphite');
    expect(activeAttribute()).toBe('graphite');
  });

  it('still applies the choice for the visit when storage is blocked', () => {
    setViewport(true);
    const blocked = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const unreadable = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setColorThemePreference('orchid');
    expect(getActiveColorTheme().id).toBe('orchid');
    blocked.mockRestore();
    unreadable.mockRestore();
  });

  it('applies and remembers the Christmas theme', () => {
    setViewport(false);
    setColorThemePreference('christmas');
    expect(window.localStorage.getItem(COLOR_THEME_STORAGE_KEY)).toBe('christmas');
    expect(getActiveColorTheme().id).toBe('christmas');
    expect(activeAttribute()).toBe('christmas');
  });
});

// index.html sets the attribute before first paint and maps it to the light
// page background: it repeats values owned by colorTheme.ts.
describe('colour theme in index.html', () => {
  it('sets the attribute from the same key, at every screen size', () => {
    expect(indexHtml).toContain(`localStorage.getItem('${COLOR_THEME_STORAGE_KEY}')`);
    expect(indexHtml).toContain(`setAttribute('${COLOR_THEME_ATTRIBUTE}',t)`);
    // No viewport gating: the stored theme applies on desktop too.
    expect(indexHtml).not.toContain('max-width: 48em');
  });

  it('has the light page background of every theme but the default', () => {
    const rules = [...indexHtml.matchAll(
      /html\[data-v365-theme='(\w+)'\]:not\(\[data-mantine-color-scheme='dark'\]\) \{ --v365-page-bg: (#[0-9a-f]{6}); \}/g,
    )];
    const inHtml = Object.fromEntries(rules.map(([, id, color]) => [id, color]));
    const expected = Object.fromEntries(
      COLOR_THEMES.filter((theme) => theme.id !== DEFAULT_COLOR_THEME).map((theme) => [theme.id, theme.lightPageBg]),
    );
    expect(inHtml).toEqual(expected);
  });
});

// Brand colours must come from the theme tuples (teal / dark), so every theme
// replaces them at every screen size; only colorTheme.ts and index.html own the hex values.
describe('no hard-coded brand colours', () => {
  const sources = import.meta.glob(['./**/*.{ts,tsx,css}', '!./**/*.test.{ts,tsx}', '!./colorTheme.ts'], {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>;
  const petrol = getColorTheme('petrol');
  const brandHex = [...petrol.primary, petrol.dark[4], petrol.dark[5], petrol.dark[6], petrol.dark[7]];

  it('scans the sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it.each(brandHex)('%s is not hard-coded outside the theme', (hex) => {
    const offenders = Object.entries(sources)
      // The PWA manifest is static (read at install time): it keeps petrol's
      // dark page colour; App.tsx updates the theme-color meta at runtime.
      .filter(([path, code]) => code.toLowerCase().includes(hex) && path !== './pwa/pwa-config.ts')
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
