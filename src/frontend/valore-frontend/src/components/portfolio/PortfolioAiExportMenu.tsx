import { useState } from 'react';
import { Button, Menu } from '@mantine/core';
import { IconCheck, IconClipboardText, IconDownload, IconSparkles } from '@tabler/icons-react';
import { getPortfolioMarkdown } from '../../services/api';

interface PortfolioAiExportMenuProps {
  portfolioId: number | null;
}

export function PortfolioAiExportMenu({ portfolioId }: PortfolioAiExportMenuProps) {
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMarkdown = async () => {
    if (portfolioId == null) return null;
    setLoading(true);
    setError(null);
    try {
      return await getPortfolioMarkdown(portfolioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export non riuscito');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    const result = await fetchMarkdown();
    if (!result) return;
    const url = window.URL.createObjectURL(new Blob([result.text], { type: 'text/markdown' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = result.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    const result = await fetchMarkdown();
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError('Copia negli appunti non disponibile');
    }
  };

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
        <Menu.Item leftSection={<IconClipboardText size={16} />} onClick={handleCopy}>
          Copia negli appunti
        </Menu.Item>
        <Menu.Item leftSection={<IconDownload size={16} />} onClick={handleDownload}>
          Scarica file .md
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
