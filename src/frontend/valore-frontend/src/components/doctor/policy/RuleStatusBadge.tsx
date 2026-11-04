import { Badge } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconClockExclamation,
  IconHelpCircle,
  IconMinus,
  IconPlayerPause,
} from '@tabler/icons-react';
import type { DoctorMetricQuality, DoctorRuleStatus } from '../../../services/api/types';
import { QUALITY_LABELS, ruleStatusMeta, type RuleTone } from './policyFormat';

const TONE_ICONS: Record<RuleTone, typeof IconCircleCheck> = {
  fail: IconCircleX,
  unknown: IconHelpCircle,
  near_limit: IconAlertTriangle,
  pass: IconCircleCheck,
  not_applicable: IconMinus,
  inactive: IconPlayerPause,
};

/** Status as icon + text (never color alone). */
export function RuleStatusBadge({ status, nearLimit, size = 'md' }: { status: DoctorRuleStatus; nearLimit: boolean; size?: 'sm' | 'md' | 'lg' }) {
  const meta = ruleStatusMeta(status, nearLimit);
  const Icon = TONE_ICONS[meta.tone];
  return (
    <Badge
      color={meta.color}
      variant="light"
      size={size}
      leftSection={<Icon size={14} aria-hidden="true" />}
      data-testid="rule-status"
      data-tone={meta.tone}
    >
      {meta.label}
    </Badge>
  );
}

export function QualityBadge({ quality }: { quality: DoctorMetricQuality | string | null | undefined }) {
  if (!quality || quality === 'ok') return null;
  const stale = quality === 'stale';
  const Icon = stale ? IconClockExclamation : IconHelpCircle;
  return (
    <Badge color={stale ? 'orange' : 'gray'} variant="outline" size="sm" leftSection={<Icon size={12} aria-hidden="true" />}>
      {QUALITY_LABELS[quality] ?? quality}
    </Badge>
  );
}
