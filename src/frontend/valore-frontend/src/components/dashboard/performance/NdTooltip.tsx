import { Text, Tooltip } from '@mantine/core';

export function NdTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip label={label} multiline w={280} withArrow>
      <Text fw={700} style={{ cursor: 'help' }}>{children}</Text>
    </Tooltip>
  );
}
