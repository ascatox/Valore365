import type { DrawerProps } from '@mantine/core';

// Bottom sheet that sizes to its content (Mantine's bottom Drawer otherwise
// takes a fixed height), capped so the page stays visible behind it.
export const BOTTOM_SHEET_PROPS: Partial<DrawerProps> = {
  position: 'bottom',
  radius: '20px 20px 0 0',
  styles: {
    content: { height: 'auto', flex: '0 0 auto', maxHeight: '90dvh' },
    body: { paddingBottom: 'calc(var(--mantine-spacing-md) + var(--safe-area-bottom))' },
  },
};
