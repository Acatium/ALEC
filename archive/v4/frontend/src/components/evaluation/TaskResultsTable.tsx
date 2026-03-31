/**
 * Task results table component (v2 - Full functionality)
 */

import { Link } from 'react-router-dom';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type { TaskResultResponse } from '@/api/types';

export interface TaskResultsTableProps {
  results: TaskResultResponse[];
  onTaskClick?: (taskId: string) => void;
  className?: string;
}

function TaskResultsTable({ results, onTaskClick, className }: TaskResultsTableProps) {
  if (results.length === 0) {
    return (
      <div className="py-8 text-center text-gray-500 dark:text-gray-400">
        No task results yet
      </div>
    );
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task ID</TableHead>
            <TableHead>Session</TableHead>
            <TableHead>Result</TableHead>
            <TableHead>Iterations</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Tests</TableHead>
            <TableHead>Outcomes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((result) => (
            <TableRow
              key={result.id || result.task_id}
              className={onTaskClick ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800' : ''}
              onClick={() => onTaskClick?.(result.task_id)}
            >
              <TableCell className="font-mono text-sm">
                {result.task_id.slice(0, 16)}
              </TableCell>
              <TableCell className="font-mono text-sm">
                {result.session_id ? (
                  <Link
                    to={`/sessions/${result.session_id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-blue-600 hover:text-blue-800 hover:underline dark:text-blue-400 dark:hover:text-blue-300"
                  >
                    {result.session_id.slice(0, 8)}
                  </Link>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </TableCell>
              <TableCell>
                <Badge
                  className={
                    result.success
                      ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                      : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                  }
                >
                  {result.success ? 'Success' : 'Failed'}
                </Badge>
              </TableCell>
              <TableCell>{result.iterations ?? '-'}</TableCell>
              <TableCell>
                {result.duration_ms != null
                  ? `${(result.duration_ms / 1000).toFixed(1)}s`
                  : '-'}
              </TableCell>
              <TableCell>
                {result.test_results ? (
                  <span className={result.test_results.failures.length > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}>
                    {result.test_results.passes.length}/{result.test_results.num_tests}
                  </span>
                ) : '-'}
              </TableCell>
              <TableCell className="text-xs">
                {result.micro_outcomes ? (
                  <span className="flex flex-wrap gap-1">
                    {result.micro_outcomes.solved > 0 && (
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 px-1.5 py-0">
                        {result.micro_outcomes.solved} solved
                      </Badge>
                    )}
                    {result.micro_outcomes.progress > 0 && (
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-1.5 py-0">
                        {result.micro_outcomes.progress} progress
                      </Badge>
                    )}
                    {result.micro_outcomes.stuck > 0 && (
                      <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300 px-1.5 py-0">
                        {result.micro_outcomes.stuck} stuck
                      </Badge>
                    )}
                    {result.micro_outcomes.error > 0 && (
                      <Badge className="bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 px-1.5 py-0">
                        {result.micro_outcomes.error} error
                      </Badge>
                    )}
                    {result.micro_outcomes.solved === 0 &&
                     result.micro_outcomes.progress === 0 &&
                     result.micro_outcomes.stuck === 0 &&
                     result.micro_outcomes.error === 0 && (
                      <span className="text-gray-400">no data</span>
                    )}
                  </span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export { TaskResultsTable };
