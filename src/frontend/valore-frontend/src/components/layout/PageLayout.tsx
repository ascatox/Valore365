import type { CSSProperties, ReactNode } from 'react';
import { Box } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';

interface PageLayoutProps {
  children: ReactNode;
  style?: CSSProperties;
}

// Pages sit on the flat app background (--v365-page-bg, see index.css);
// cards carry their own surface, so no per-page gradients.
export function PageLayout({
  children,
  style,
}: PageLayoutProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');

  return (
    <Box
      style={{
        minHeight: '100%',
        paddingTop: 'var(--mantine-spacing-sm)',
        // On mobile AppShell.Main already reserves room for the bottom nav.
        paddingBottom: 'var(--mantine-spacing-sm)',
        paddingInline: isMobile ? 'var(--mantine-spacing-xs)' : 'var(--mantine-spacing-sm)',
        ...style,
      }}
    >
      {children}
    </Box>
  );
}
