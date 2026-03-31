/**
 * Micro-outcome badge component
 */

import { cn } from '@/lib/utils';
import { microOutcomeToLabel, microOutcomeToColor } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import { CheckIcon, ArrowRightIcon, PauseIcon, AlertCircleIcon } from '@/components/ui/Icons';
import type { MicroOutcome } from '@/api/types';

export interface MicroOutcomeBadgeProps {
  outcome: MicroOutcome | null;
  className?: string;
  showIcon?: boolean;
}

function MicroOutcomeBadge({ outcome, className, showIcon = true }: MicroOutcomeBadgeProps) {
  if (!outcome) return null;

  const icons = {
    progress: <ArrowRightIcon className="h-3 w-3" />,
    solved: <CheckIcon className="h-3 w-3" />,
    stuck: <PauseIcon className="h-3 w-3" />,
    error: <AlertCircleIcon className="h-3 w-3" />,
  };

  return (
    <Badge className={cn('gap-1', microOutcomeToColor(outcome), className)}>
      {showIcon && icons[outcome]}
      {microOutcomeToLabel(outcome)}
    </Badge>
  );
}

export { MicroOutcomeBadge };
