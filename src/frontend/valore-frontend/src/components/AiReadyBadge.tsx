import { useId } from 'react';
import { useComputedColorScheme } from '@mantine/core';

interface AiReadyBadgeProps {
  /** Rendered height in px; width follows the badge aspect ratio. */
  height?: number;
}

const VIEWBOX_WIDTH = 142;
const VIEWBOX_HEIGHT = 32;
const FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const PALETTE = {
  light: {
    background: '#ecfdf5',
    border: '#a7f3d0',
    label: '#1e3a8a',
    divider: '#a7f3d0',
    protocol: '#059669',
  },
  dark: {
    background: 'rgba(16, 185, 129, 0.12)',
    border: 'rgba(16, 185, 129, 0.35)',
    label: '#ffffff',
    divider: 'rgba(16, 185, 129, 0.35)',
    protocol: '#63e6be',
  },
} as const;

/**
 * "AI Ready · MCP" pill: signals that a Valore365 portfolio can be connected
 * (read-only, via MCP) to AI assistants. Brand colors follow logo-mark.svg
 * (navy #1e3a8a -> emerald #10b981) and adapt to the color scheme.
 */
export function AiReadyBadge({ height = 32 }: AiReadyBadgeProps) {
  const isDark = useComputedColorScheme('light') === 'dark';
  const colors = isDark ? PALETTE.dark : PALETTE.light;
  const gradientId = `ai-ready-gradient-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const width = (height * VIEWBOX_WIDTH) / VIEWBOX_HEIGHT;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
      role="img"
      aria-label="AI Ready: compatibile con MCP"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <title>AI Ready: compatibile con MCP</title>
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <rect
        x="0.5"
        y="0.5"
        width={VIEWBOX_WIDTH - 1}
        height={VIEWBOX_HEIGHT - 1}
        rx={(VIEWBOX_HEIGHT - 1) / 2}
        fill={colors.background}
        stroke={colors.border}
      />
      <circle cx="16" cy="16" r="11" fill={`url(#${gradientId})`} />
      <path d="M16 9.5 Q17 15 22.5 16 Q17 17 16 22.5 Q15 17 9.5 16 Q15 15 16 9.5Z" fill="#ffffff" />
      <text
        x="33"
        y="20.5"
        fontFamily={FONT_FAMILY}
        fontSize="13"
        fontWeight="700"
        fill={colors.label}
        textLength="56"
        lengthAdjust="spacingAndGlyphs"
      >
        AI Ready
      </text>
      <line x1="97" y1="9" x2="97" y2="23" stroke={colors.divider} strokeWidth="1" />
      <text
        x="105"
        y="20.5"
        fontFamily={FONT_FAMILY}
        fontSize="11"
        fontWeight="800"
        fill={colors.protocol}
        textLength="24"
        lengthAdjust="spacingAndGlyphs"
      >
        MCP
      </text>
    </svg>
  );
}
