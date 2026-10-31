import { Button, Menu } from '@mantine/core';
import { IconCheck, IconClipboardText, IconDownload, IconSparkles } from '@tabler/icons-react';
import type { PortfolioScopeInput } from '../../scope/portfolioScope';
import { usePortfolioAiExport } from './hooks/usePortfolioAiExport';

interface PortfolioAiExportMenuProps {
  /** Portfolio id or scope; an aggregate exports the merged "vista aggregata". */
  scope: PortfolioScopeInput;
  /** Share the page's export state (alerts) instead of a local one. */
  exportState?: ReturnType<typeof usePortfolioAiExport>;
}

export function PortfolioAiExportMenu({ scope, exportState }: PortfolioAiExportMenuProps) {
  const ownState = usePortfolioAiExport(scope);
  const { copyForAi, downloadMarkdown, loading, copied, error, isAggregate } = exportState ?? ownState;

  return (
    <Menu shadow="md" position="bottom-end" radius="md">
      <Menu.Target>
        <Button
          variant="light"
          leftSection={copied ? <IconCheck size={16} /> : <IconSparkles size={16} />}
          loading={loading}
          disabled={scope == null}
          color={error ? 'red' : copied ? 'teal' : undefined}
        >
          {error ? 'Export fallito' : copied ? 'Copiato!' : 'Esporta per AI'}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{isAggregate ? 'Snapshot della vista aggregata in Markdown' : 'Snapshot del portafoglio in Markdown'}</Menu.Label>
        <Menu.Item leftSection={<IconClipboardText size={16} />} onClick={copyForAi}>
          Copia negli appunti
        </Menu.Item>
        <Menu.Item leftSection={<IconDownload size={16} />} onClick={downloadMarkdown}>
          Scarica file .md
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
