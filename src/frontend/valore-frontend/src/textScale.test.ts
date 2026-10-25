import { MAX_TEXT_SCALE, MIN_TEXT_SCALE, textScaleFromIosBodySize } from './textScale';

describe('textScaleFromIosBodySize', () => {
  it('keeps the default iOS text size at scale 1', () => {
    expect(textScaleFromIosBodySize(17)).toBe(1);
  });

  it('follows larger and smaller iOS text sizes', () => {
    expect(textScaleFromIosBodySize(19)).toBeCloseTo(19 / 17, 3);
    expect(textScaleFromIosBodySize(15)).toBeCloseTo(15 / 17, 3);
  });

  it('caps the accessibility sizes so the mobile layout holds', () => {
    expect(textScaleFromIosBodySize(53)).toBe(MAX_TEXT_SCALE);
    expect(textScaleFromIosBodySize(12)).toBe(MIN_TEXT_SCALE);
  });

  it('falls back to 1 for unreadable sizes', () => {
    expect(textScaleFromIosBodySize(Number.NaN)).toBe(1);
    expect(textScaleFromIosBodySize(0)).toBe(1);
  });
});
