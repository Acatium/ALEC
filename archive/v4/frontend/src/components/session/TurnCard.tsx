/**
 * Turn card component
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { formatRelativeTime, truncate } from '@/lib/utils';
import { Card, CardContent, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ChevronRightIcon } from '@/components/ui/Icons';
import { MicroOutcomeBadge } from './MicroOutcomeBadge';
import { BulletAttribution } from './BulletAttribution';
import type { Turn } from '@/api/types';

export interface TurnCardProps {
  turn: Turn;
  className?: string;
}

function TurnCard({ turn, className }: TurnCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="cursor-pointer p-4" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-start justify-between gap-4">
          {/* Turn number and outcome */}
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
              {turn.turn_number}
            </div>
            <MicroOutcomeBadge outcome={turn.micro_outcome} />
          </div>

          {/* Expand button */}
          <Button variant="ghost" size="icon" className="shrink-0">
            <ChevronRightIcon
              className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')}
            />
          </Button>
        </div>

        {/* Preview */}
        <div className="mt-2 space-y-1">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            <span className="font-medium">User:</span>{' '}
            {truncate(turn.user_message, 100)}
          </p>
          {!expanded && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              <span className="font-medium">Assistant:</span>{' '}
              {truncate(turn.assistant_response, 100)}
            </p>
          )}
        </div>
      </CardHeader>

      {/* Expanded content */}
      {expanded && (
        <CardContent className="border-t border-gray-200 pt-4 dark:border-gray-800">
          {/* User message */}
          <div className="mb-4">
            <h4 className="mb-1 text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
              User Message
            </h4>
            <div className="whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
              {turn.user_message}
            </div>
          </div>

          {/* Assistant response */}
          <div className="mb-4">
            <h4 className="mb-1 text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
              Assistant Response
            </h4>
            <div className="whitespace-pre-wrap rounded-lg bg-blue-50 p-3 text-sm dark:bg-blue-900/20">
              {turn.assistant_response}
            </div>
          </div>

          {/* Sub-task */}
          {turn.sub_task && (
            <div className="mb-4">
              <h4 className="mb-1 text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                Sub-task
              </h4>
              <p className="text-sm">{turn.sub_task}</p>
            </div>
          )}

          {/* Error trace */}
          {turn.error_trace && (
            <div className="mb-4">
              <h4 className="mb-1 text-xs font-medium uppercase text-red-500">Error</h4>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-red-50 p-3 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
                {turn.error_trace}
              </pre>
            </div>
          )}

          {/* Bullet attribution */}
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
              Bullet Attribution
            </h4>
            <BulletAttribution
              helped={turn.bullets_helped}
              harmed={turn.bullets_harmed}
              shown={turn.bullets_shown}
            />
          </div>

          {/* Timestamp */}
          <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
            {formatRelativeTime(turn.created_at)}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

export { TurnCard };
