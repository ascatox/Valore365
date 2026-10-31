import type { ReactNode } from 'react';
import { Alert, Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconStack2 } from '@tabler/icons-react';
import { useOptionalPortfolioScope } from './PortfolioScopeContext';
import { AGGREGATE_READ_ONLY_HINT, AGGREGATE_UNAVAILABLE } from './aggregateLabels';

interface ReadOnlyTooltipProps {
  /** True in the aggregate view: the wrapped (disabled) control gets the explanation. */
  active: boolean;
  label?: string;
  children: ReactNode;
}

/**
 * Tooltip explaining why a write action is disabled in the aggregate view.
 * A disabled button gets no pointer events, so the tooltip hangs on a
 * wrapping span. When not active the children render untouched.
 */
export function AggregateReadOnlyTooltip({ active, label = AGGREGATE_READ_ONLY_HINT, children }: ReadOnlyTooltipProps) {
  if (!active) return <>{children}</>;
  return (
    <Tooltip label={label} withArrow>
      <span style={{ display: 'inline-flex' }} tabIndex={0} data-aggregate-read-only="">
        {children}
      </span>
    </Tooltip>
  );
}

interface UnavailableNoticeProps {
  /** What is missing, e.g. "La liquidità è gestita per singolo portafoglio." */
  description?: ReactNode;
  mb?: string;
}

/** Short notice in place of a section that exists only for a single portfolio. */
export function AggregateUnavailableNotice({ description, mb }: UnavailableNoticeProps) {
  return (
    <Alert color="gray" variant="light" icon={<IconStack2 size={18} />} title={AGGREGATE_UNAVAILABLE} mb={mb}>
      {description ?? AGGREGATE_READ_ONLY_HINT}
    </Alert>
  );
}

/**
 * Friendly notice after an aggregate request failed with a scope error (a
 * portfolio deleted in another tab, mixed currencies). The scope context has
 * already started the recovery; this only tells the user what happened.
 */
export function AggregateScopeNotice({ mb = 'md' }: { mb?: string }) {
  const context = useOptionalPortfolioScope();
  if (!context?.scopeNotice) return null;
  return (
    <Alert
      color="yellow"
      variant="light"
      mb={mb}
      icon={<IconAlertTriangle size={18} />}
      title="Vista aggregata aggiornata"
      withCloseButton
      closeButtonLabel="Chiudi avviso"
      onClose={context.dismissScopeNotice}
      role="status"
    >
      {context.scopeNotice}
    </Alert>
  );
}
