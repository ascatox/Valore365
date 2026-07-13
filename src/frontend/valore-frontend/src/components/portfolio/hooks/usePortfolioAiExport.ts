import { useState } from 'react';
import { getPortfolioMarkdown } from '../../../services/api';

export function usePortfolioAiExport(portfolioId: number | null) {
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

  const downloadMarkdown = async () => {
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

  const copyForAi = async () => {
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

  return { copyForAi, downloadMarkdown, loading, copied, error };
}
