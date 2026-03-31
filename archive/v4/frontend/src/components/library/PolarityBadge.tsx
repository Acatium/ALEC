/**
 * Polarity badge component
 */

import { cn } from '@/lib/utils';
import { polarityToLabel, polarityToColor } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import type { BulletPolarity } from '@/api/types';

export interface PolarityBadgeProps {
  polarity: BulletPolarity;
  className?: string;
}

function PolarityBadge({ polarity, className }: PolarityBadgeProps) {
  return (
    <Badge className={cn(polarityToColor(polarity), className)}>
      {polarityToLabel(polarity)}
    </Badge>
  );
}

export { PolarityBadge };
