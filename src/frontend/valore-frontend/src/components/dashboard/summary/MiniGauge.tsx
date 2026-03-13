interface MiniGaugeProps {
  /** Percentage value (e.g. -2.5 for -2.5%) */
  value: number;
  /** Max absolute percentage for full-scale deflection (default 5) */
  max?: number;
  /** Width/height of the gauge SVG (default 48) */
  size?: number;
}

/**
 * Small semicircular gauge that shows a needle position
 * based on a percentage value. Green when positive, red when negative.
 */
export function MiniGauge({ value, max = 5, size = 48 }: MiniGaugeProps) {
  const clamped = Math.max(-max, Math.min(max, value));
  // Map [-max, +max] to [π, 0] (left to right semicircle)
  const ratio = (clamped + max) / (2 * max); // 0..1
  const angle = Math.PI * (1 - ratio); // π..0

  const cx = size / 2;
  const cy = size * 0.72;
  const r = size * 0.38;
  const needleLen = r * 0.85;

  const needleX = cx + needleLen * Math.cos(angle);
  const needleY = cy - needleLen * Math.sin(angle);

  const color = value >= 0 ? '#16a34a' : '#dc2626';
  const trackGray = '#e2e8f0';

  // Arc path for the semicircle track
  const arcStartX = cx - r;
  const arcEndX = cx + r;
  const arcY = cy;

  return (
    <svg width={size} height={size * 0.62} viewBox={`0 0 ${size} ${size * 0.62}`} style={{ display: 'block' }}>
      {/* Track arc */}
      <path
        d={`M ${arcStartX} ${arcY} A ${r} ${r} 0 0 1 ${arcEndX} ${arcY}`}
        fill="none"
        stroke={trackGray}
        strokeWidth={3}
        strokeLinecap="round"
      />
      {/* Colored arc from center to current value */}
      {Math.abs(clamped) > 0.01 && (() => {
        const centerAngle = Math.PI / 2; // top center = 0%
        const startA = clamped >= 0 ? angle : centerAngle;
        const endA = clamped >= 0 ? centerAngle : angle;
        const sx = cx + r * Math.cos(endA);
        const sy = cy - r * Math.sin(endA);
        const ex = cx + r * Math.cos(startA);
        const ey = cy - r * Math.sin(startA);
        const largeArc = (endA - startA) > Math.PI ? 1 : 0;
        return (
          <path
            d={`M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 0 ${ex} ${ey}`}
            fill="none"
            stroke={color}
            strokeWidth={3}
            strokeLinecap="round"
            opacity={0.7}
          />
        );
      })()}
      {/* Needle */}
      <line
        x1={cx}
        y1={cy}
        x2={needleX}
        y2={needleY}
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
      />
      {/* Center dot */}
      <circle cx={cx} cy={cy} r={2.5} fill={color} />
    </svg>
  );
}
