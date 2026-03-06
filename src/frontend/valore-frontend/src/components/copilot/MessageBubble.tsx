import { Box, Paper, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconRobot } from '@tabler/icons-react';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

export function MessageBubble({ role, content, streaming }: MessageBubbleProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isUser = role === 'user';

  return (
    <Box
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        gap: 8,
        alignItems: 'flex-start',
      }}
    >
      {!isUser && (
        <Box
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: isDark ? theme.colors.teal[8] : theme.colors.teal[1],
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          <IconRobot size={16} color={isDark ? theme.colors.teal[2] : theme.colors.teal[7]} />
        </Box>
      )}
      <Paper
        shadow="xs"
        radius="lg"
        px="md"
        py="sm"
        style={{
          maxWidth: '80%',
          background: isUser
            ? (isDark ? theme.colors.blue[8] : theme.colors.blue[5])
            : (isDark ? theme.colors.dark[6] : theme.colors.gray[0]),
          color: isUser
            ? '#fff'
            : (isDark ? theme.colors.gray[1] : theme.colors.dark[8]),
          borderBottomRightRadius: isUser ? 4 : undefined,
          borderBottomLeftRadius: !isUser ? 4 : undefined,
        }}
      >
        <Text
          size="sm"
          style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}
        >
          {content || (streaming ? '...' : '')}
        </Text>
      </Paper>
    </Box>
  );
}
