import { Box, Group, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import logoMark from '../assets/logo-mark.svg';

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const mobileBoost = compact && isMobile ? 2 : 0;
  const logoSize = (compact ? 26 : 30) + mobileBoost;
  const logoRadius = (compact ? 8 : 10) + (mobileBoost > 0 ? 1 : 0);

  return (
    <Group gap={compact ? 8 : 10} wrap="nowrap">
      <Box
        style={{
          width: logoSize,
          height: logoSize,
          minWidth: logoSize,
          borderRadius: logoRadius,
          overflow: 'hidden',
          background: isDark ? theme.colors.dark[6] : '#ffffff',
          border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(15, 23, 42, 0.06)',
          boxShadow: isDark ? '0 8px 18px rgba(0, 0, 0, 0.24)' : '0 8px 18px rgba(15, 23, 42, 0.10)',
        }}
      >
        <img
          src={logoMark}
          alt="Logo Valore365"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: 'block',
            padding: compact ? 3 : 2,
            boxSizing: 'border-box',
          }}
        />
      </Box>

      <Text
        fw={800}
        c={isDark ? theme.white : theme.black}
        style={{
          letterSpacing: -0.3,
          lineHeight: 1,
          fontSize: compact && isMobile ? 21 : undefined,
        }}
      >
        Valore365
      </Text>
    </Group>
  );
}
