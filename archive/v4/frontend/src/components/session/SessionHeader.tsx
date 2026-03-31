/**
 * Session header component
 */

import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { formatDate, statusToColor } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ChevronLeftIcon } from '@/components/ui/Icons';
import type { SessionMetadata } from '@/api/types';

export interface SessionHeaderProps {
  session: SessionMetadata;
  className?: string;
}

function SessionHeader({ session, className }: SessionHeaderProps) {
  return (
    <div className={cn('space-y-4', className)}>
      {/* Back link */}
      <Link to="/sessions">
        <Button variant="ghost" size="sm" className="gap-1">
          <ChevronLeftIcon className="h-4 w-4" />
          Back to Sessions
        </Button>
      </Link>

      {/* Title and status */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {session.title || `Session ${session.session_id.slice(0, 8)}`}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {session.session_id}
          </p>
        </div>
        <Badge className={statusToColor(session.status)}>{session.status}</Badge>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap gap-6 text-sm">
        <div>
          <span className="text-gray-500 dark:text-gray-400">Domain:</span>{' '}
          <span className="font-medium">{session.domain}</span>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Messages:</span>{' '}
          <span className="font-medium">{session.message_count}</span>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Created:</span>{' '}
          <span className="font-medium">{formatDate(session.created_at)}</span>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Updated:</span>{' '}
          <span className="font-medium">{formatDate(session.updated_at)}</span>
        </div>
      </div>
    </div>
  );
}

export { SessionHeader };
