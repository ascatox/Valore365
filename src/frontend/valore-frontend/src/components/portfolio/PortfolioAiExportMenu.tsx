import { Button, Menu } from '@mantine/core';
import { IconCheck, IconClipboardText, IconDownload, IconSparkles } from '@tabler/icons-react';
import { usePortfolioAiExport } from './hooks/usePortfolioAiExport';

interface PortfolioAiExportMenuProps {
  portfolioId: number | null;
}

export function PortfolioAiExportMenu({ portfolioId }: PortfolioAiExportMenuProps) {
  const { copyForAi, downloadMarkdown, loading, copied, error } = usePortfolioAiExport(portfolioId);

  return (
    <Menu shadow="md" position="bottom-end" radius="md">
      <Menu.Target>
        <Button
          variant="light"
          leftSection={copied ? <IconCheck size={16} /> : <IconSparkles size={16} />}
          loading={loading}
          disabled={portfolioId == null}
          color={error ? 'red' : copied ? 'teal' : undefined}
        >
          {error ? 'Export fallito' : copied ? 'Copiato!' : 'Esporta per AI'}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Snapshot del portafoglio in Markdown</Menu.Label>
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
