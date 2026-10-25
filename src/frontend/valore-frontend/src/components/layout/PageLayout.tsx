import type { CSSProperties, ReactNode } from 'react';
import { Box } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';

interface PageLayoutProps {
  children: ReactNode;
  mobileBottomPadding?: number | string;
  style?: CSSProperties;
}

// Pages sit on the flat app background (--v365-page-bg, see index.css);
// cards carry their own surface, so no per-page gradients.
export function PageLayout({
  children,
  mobileBottomPadding,
  style,
}: PageLayoutProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');

  return (
    <Box
      style={{
        minHeight: '100%',
        paddingTop: 'var(--mantine-spacing-sm)',
        paddingBottom: (isMobile ? mobileBottomPadding : undefined) ?? 'var(--mantine-spacing-sm)',
        paddingInline: isMobile ? 'var(--mantine-spacing-xs)' : 'var(--mantine-spacing-sm)',
        ...style,
      }}
    >
      {children}
    </Box>
  );
}
