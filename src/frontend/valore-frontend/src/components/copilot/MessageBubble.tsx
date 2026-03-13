import React, { useRef, useEffect } from 'react';
import { Box, Paper, Text, useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconRobot } from '@tabler/icons-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const COPILOT_FONT = "'DM Sans', system-ui, sans-serif";
const COPILOT_DISCLAIMER = 'Supporto informativo, non consulenza finanziaria.';

/**
 * After ReactMarkdown renders, inject data-label attributes on <td> elements
 * so the CSS card layout on mobile can show column headers inline.
 */
function useTableDataLabels(ref: React.RefObject<HTMLDivElement | null>, content: string) {
  useEffect(() => {
    if (!ref.current) return;
    const tables = ref.current.querySelectorAll('table');
    tables.forEach((table) => {
      const headers: string[] = [];
      table.querySelectorAll('thead th').forEach((th) => {
        headers.push(th.textContent?.trim() || '');
      });
      if (headers.length === 0) return;
      table.querySelectorAll('tbody tr').forEach((tr) => {
        tr.querySelectorAll('td').forEach((td, i) => {
          if (headers[i]) td.setAttribute('data-label', headers[i]);
        });
      });
    });
  }, [ref, content]);
}

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  thinkingStatus?: string | null;
}

export function MessageBubble({ role, content, streaming, thinkingStatus }: MessageBubbleProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isUser = role === 'user';
  const normalizedContent = content.toLowerCase();
  const hasDisclaimer = normalizedContent.includes('supporto informativo') || normalizedContent.includes('consulenza finanziaria');
  const mdRef = useRef<HTMLDivElement | null>(null);
  useTableDataLabels(mdRef, content);

  const renderContent = () => {
    if (thinkingStatus && !content) {
      return (
        <Text
          size="sm"
          c="dimmed"
          style={{
            fontFamily: COPILOT_FONT,
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
            fontStyle: 'italic',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        >
          {thinkingStatus}
        </Text>
      );
    }

    if (!content && streaming) {
      return (
        <Text size="sm" style={{ fontFamily: COPILOT_FONT, lineHeight: 1.6 }}>
          ...
        </Text>
      );
    }

    // User messages: plain text
    if (isUser) {
      return (
        <Text
          size="sm"
          style={{
            fontFamily: COPILOT_FONT,
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
            letterSpacing: '-0.01em',
          }}
        >
          {content}
        </Text>
      );
    }

    // Assistant messages: render Markdown
    return (
      <Box
        ref={mdRef}
        className="copilot-markdown"
        style={{
          fontFamily: COPILOT_FONT,
          fontSize: 'var(--mantine-font-size-sm)',
          lineHeight: 1.6,
          letterSpacing: '-0.01em',
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </Box>
    );
  };

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
          maxWidth: isUser ? '80%' : '92%',
          minWidth: 0,
          overflow: 'hidden',
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
        {renderContent()}
        {!isUser && content && !hasDisclaimer && (
          <Text
            size="xs"
            mt="sm"
            c={isDark ? theme.colors.gray[4] : theme.colors.gray[7]}
            style={{
              fontFamily: COPILOT_FONT,
              borderTop: `1px solid ${isDark ? theme.colors.dark[4] : theme.colors.gray[3]}`,
              paddingTop: 8,
            }}
          >
            {COPILOT_DISCLAIMER}
          </Text>
        )}
      </Paper>
    </Box>
  );
}
