import { useState } from 'react';
import { getPortfolioMarkdownForScope } from '../../../services/api';
import { friendlyAggregateError } from '../../../scope/aggregateErrors';
import { useOptionalPortfolioScope } from '../../../scope/PortfolioScopeContext';
import { toPortfolioScope, type PortfolioScopeInput } from '../../../scope/portfolioScope';

/**
 * Markdown snapshot for an external AI: copy to the clipboard or download.
 * A single portfolio uses `/portfolios/{id}/export/markdown`, an aggregate
 * scope `/portfolios/aggregate/export/markdown` (merged data, the included
 * portfolios listed in the header).
 */
export function usePortfolioAiExport(scopeInput: PortfolioScopeInput) {
  const scope = toPortfolioScope(scopeInput);
  const scopeContext = useOptionalPortfolioScope();
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMarkdown = async () => {
    if (scope == null) return null;
    setLoading(true);
    setError(null);
    try {
      return await getPortfolioMarkdownForScope(scope);
    } catch (err) {
      // A stale aggregate (portfolio deleted elsewhere) also refreshes the scope.
      if (scope.mode === 'aggregate') scopeContext?.reportScopeError(err);
      setError((scope.mode === 'aggregate' ? friendlyAggregateError(err) : null)
        ?? (err instanceof Error ? err.message : null)
        ?? 'Export non riuscito');
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

  return { copyForAi, downloadMarkdown, loading, copied, error, isAggregate: scope?.mode === 'aggregate' };
}
