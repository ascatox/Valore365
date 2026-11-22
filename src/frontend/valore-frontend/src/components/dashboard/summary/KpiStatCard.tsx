import { Paper, Text, ThemeIcon } from '@mantine/core';
import type { KpiStatCardProps } from '../types';

// The label may wrap onto two lines in narrow columns (tablet with sidebar):
// the icon stays top-right and the value sits at the bottom of the card, so
// values line up across the row whatever the label length.
export function KpiStatCard({ label, value, color, icon: Icon, iconColor }: KpiStatCardProps) {
  return (
    <Paper withBorder p="sm" radius="md" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 4, containerType: 'inline-size' }}>
      {/* The icon floats so a wrapped label's second line can run under it. */}
      <div style={{ display: 'flow-root' }}>
        {Icon && (
          <ThemeIcon
            color={iconColor ?? 'teal'}
            variant="light"
            size="sm"
            radius="md"
            // Ends the float within the first label line (22px icon, ~19px line).
            style={{ float: 'right', marginLeft: 8, marginBottom: -4 }}
          >
            <Icon size={14} />
          </ThemeIcon>
        )}
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      </div>
      {/* One line always: the size follows the card width (container query
          units), up to Mantine's lg, so "+101.665,32 €" fits five columns on a
          tablet with the sidebar open. */}
      <Text fw={700} c={color ?? undefined} style={{ whiteSpace: 'nowrap', fontSize: 'clamp(0.8125rem, 11.5cqi, var(--mantine-font-size-lg))' }}>
        {value}
      </Text>
    </Paper>
  );
}
