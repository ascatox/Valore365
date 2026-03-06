import { Box, Group, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import logoMark from '../assets/logo-mark.svg';

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  return (
    <Group gap={compact ? 8 : 10} wrap="nowrap">
      <Box
        style={{
          width: compact ? 26 : 30,
          height: compact ? 26 : 30,
          minWidth: compact ? 26 : 30,
          borderRadius: compact ? 8 : 10,
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
        size={compact ? 'md' : 'lg'}
        c={isDark ? theme.white : theme.black}
        style={{ letterSpacing: -0.3, lineHeight: 1 }}
      >
        Valore365
      </Text>
    </Group>
  );
}
