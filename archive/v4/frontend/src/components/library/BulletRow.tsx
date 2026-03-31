/**
 * AKU row component (v4)
 */

import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { truncate, formatRelativeTime, statusToColor, calculateEffectiveness, formatPercent } from '@/lib/utils';
import { TableRow, TableCell } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import type { BulletResponse } from '@/api/types';

export interface BulletRowProps {
  bullet: BulletResponse;
  selected?: boolean;
  onSelect?: (id: string) => void;
}

function BulletRow({ bullet, selected, onSelect }: BulletRowProps) {
  const effectiveness = calculateEffectiveness(
    bullet.helpful_count,
    bullet.harmful_count,
    bullet.neutral_count
  );

  return (
    <TableRow className={cn(selected && 'bg-blue-50 dark:bg-blue-900/20')}>
      {/* Selection checkbox */}
      {onSelect && (
        <TableCell>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onSelect(bullet.id)}
            className="h-4 w-4 rounded border-gray-300"
          />
        </TableCell>
      )}

      {/* Situation */}
      <TableCell>
        <Link
          to={`/bullets/${bullet.id}`}
          className="font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          {truncate(bullet.situation, 50)}
        </Link>
      </TableCell>

      {/* Assertion */}
      <TableCell className="max-w-xs">
        <span className="text-sm text-gray-600 dark:text-gray-300">
          {truncate(bullet.assertion, 60)}
        </span>
      </TableCell>

      {/* Status */}
      <TableCell>
        <Badge className={statusToColor(bullet.status)}>{bullet.status}</Badge>
      </TableCell>

      {/* Effectiveness */}
      <TableCell>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'font-medium',
              effectiveness >= 0.7
                ? 'text-green-600 dark:text-green-400'
                : effectiveness >= 0.4
                  ? 'text-yellow-600 dark:text-yellow-400'
                  : 'text-red-600 dark:text-red-400'
            )}
          >
            {formatPercent(effectiveness)}
          </span>
          <span className="text-xs text-gray-500">
            ({bullet.helpful_count}+/{bullet.harmful_count}-)
          </span>
        </div>
      </TableCell>

      {/* Created */}
      <TableCell className="text-gray-500 dark:text-gray-400">
        {formatRelativeTime(bullet.created_at)}
      </TableCell>
    </TableRow>
  );
}

export { BulletRow };
