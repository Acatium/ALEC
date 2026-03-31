/**
 * Message component (v4)
 */

import { cn, truncate } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/utils';
import type { BulletUsed } from '@/api/types';
import { Badge } from '@/components/ui/Badge';

export interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  isOptimistic?: boolean;
  bulletsUsed?: BulletUsed[];
}

function Message({ role, content, timestamp, isOptimistic, bulletsUsed }: MessageProps) {
  const isUser = role === 'user';

  return (
    <div
      className={cn(
        'flex flex-col gap-2',
        isUser ? 'items-end' : 'items-start',
        isOptimistic && 'opacity-70'
      )}
    >
      {/* Message bubble */}
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3',
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
        )}
      >
        <div className="whitespace-pre-wrap text-sm">{content}</div>
      </div>

      {/* Timestamp */}
      {timestamp && (
        <span className="px-2 text-xs text-gray-500 dark:text-gray-400">
          {formatRelativeTime(timestamp)}
        </span>
      )}

      {/* AKUs used (only for assistant messages) */}
      {!isUser && bulletsUsed && bulletsUsed.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1 px-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">AKUs used:</span>
          {bulletsUsed.slice(0, 3).map((bullet) => (
            <Badge
              key={bullet.id}
              className="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
              title={bullet.assertion}
            >
              {truncate(bullet.situation, 25)}
            </Badge>
          ))}
          {bulletsUsed.length > 3 && (
            <span className="text-xs text-gray-500">+{bulletsUsed.length - 3} more</span>
          )}
        </div>
      )}
    </div>
  );
}

export { Message };
