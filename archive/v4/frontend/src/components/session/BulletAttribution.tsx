/**
 * Bullet attribution component
 */

import { cn } from '@/lib/utils';
import { ThumbsUpIcon, ThumbsDownIcon } from '@/components/ui/Icons';

export interface BulletAttributionProps {
  helped: string[];
  harmed: string[];
  shown: string[];
  className?: string;
}

function BulletAttribution({ helped, harmed, shown, className }: BulletAttributionProps) {
  // Calculate irrelevant (shown but neither helped nor harmed)
  const helpedSet = new Set(helped);
  const harmedSet = new Set(harmed);
  const irrelevant = shown.filter((id) => !helpedSet.has(id) && !harmedSet.has(id));

  if (shown.length === 0) {
    return (
      <div className={cn('text-sm text-gray-500 dark:text-gray-400', className)}>
        No bullets shown
      </div>
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      {/* Helped */}
      {helped.length > 0 && (
        <div className="flex items-center gap-2">
          <ThumbsUpIcon className="h-4 w-4 text-green-600 dark:text-green-400" />
          <span className="text-sm text-green-600 dark:text-green-400">
            {helped.length} helped
          </span>
          <div className="flex gap-1">
            {helped.slice(0, 3).map((id) => (
              <span
                key={id}
                className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-300"
              >
                {id.slice(0, 8)}
              </span>
            ))}
            {helped.length > 3 && (
              <span className="text-xs text-gray-500">+{helped.length - 3}</span>
            )}
          </div>
        </div>
      )}

      {/* Harmed */}
      {harmed.length > 0 && (
        <div className="flex items-center gap-2">
          <ThumbsDownIcon className="h-4 w-4 text-red-600 dark:text-red-400" />
          <span className="text-sm text-red-600 dark:text-red-400">{harmed.length} harmed</span>
          <div className="flex gap-1">
            {harmed.slice(0, 3).map((id) => (
              <span
                key={id}
                className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300"
              >
                {id.slice(0, 8)}
              </span>
            ))}
            {harmed.length > 3 && (
              <span className="text-xs text-gray-500">+{harmed.length - 3}</span>
            )}
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {shown.length} shown total
        {irrelevant.length > 0 && ` (${irrelevant.length} neutral)`}
      </div>
    </div>
  );
}

export { BulletAttribution };
