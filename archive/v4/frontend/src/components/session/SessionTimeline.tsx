/**
 * Session timeline component
 */

import { cn } from '@/lib/utils';
import { TurnCard } from './TurnCard';
import { EmptyState } from '@/components/shared/EmptyState';
import { MessageSquareIcon } from '@/components/ui/Icons';
import type { Turn } from '@/api/types';

export interface SessionTimelineProps {
  turns: Turn[];
  className?: string;
}

function SessionTimeline({ turns, className }: SessionTimelineProps) {
  if (turns.length === 0) {
    return (
      <EmptyState
        icon={<MessageSquareIcon className="h-12 w-12" />}
        title="No turns yet"
        description="This session has no conversation turns"
        className={className}
      />
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {turns.map((turn) => (
        <TurnCard key={turn.turn_id} turn={turn} />
      ))}
    </div>
  );
}

export { SessionTimeline };
