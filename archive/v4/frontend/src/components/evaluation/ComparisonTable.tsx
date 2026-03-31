/**
 * Comparison table for experiments (v2 - Full functionality)
 */

import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type { ExperimentSummary } from '@/api/types';

export interface ComparisonTableProps {
  experiments: ExperimentSummary[];
  highlightBest?: boolean;
  className?: string;
}

function ComparisonTable({ experiments, highlightBest = true, className }: ComparisonTableProps) {
  if (experiments.length === 0) {
    return (
      <div className="py-8 text-center text-gray-500 dark:text-gray-400">
        No experiments to compare
      </div>
    );
  }

  // Find best success rate
  const bestSuccessRate = highlightBest
    ? Math.max(...experiments.map((e) => e.success_rate ?? 0))
    : null;

  return (
    <div className={cn('overflow-x-auto', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Experiment</TableHead>
            <TableHead>Dataset</TableHead>
            <TableHead>Tasks</TableHead>
            <TableHead>Task Success %</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {experiments.map((experiment) => {
            const isBest =
              highlightBest &&
              experiment.success_rate != null &&
              experiment.success_rate === bestSuccessRate;

            return (
              <TableRow
                key={experiment.id}
                className={isBest ? 'bg-green-50 dark:bg-green-900/20' : ''}
              >
                <TableCell>
                  <div>
                    <span className="font-medium">{experiment.name}</span>
                    {isBest && (
                      <Badge className="ml-2 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                        Best
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {experiment.experiment_type}
                  </p>
                </TableCell>
                <TableCell>{experiment.dataset_split || '-'}</TableCell>
                <TableCell>
                  {experiment.tasks_completed} / {experiment.tasks_total}
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      'font-semibold',
                      experiment.success_rate != null && experiment.success_rate >= 0.7
                        ? 'text-green-600 dark:text-green-400'
                        : experiment.success_rate != null && experiment.success_rate >= 0.5
                          ? 'text-yellow-600 dark:text-yellow-400'
                          : 'text-red-600 dark:text-red-400'
                    )}
                  >
                    {experiment.success_rate != null
                      ? `${(experiment.success_rate * 100).toFixed(1)}%`
                      : '-'}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    className={cn(
                      experiment.status === 'completed'
                        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                        : experiment.status === 'running'
                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                          : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
                    )}
                  >
                    {experiment.status}
                  </Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export { ComparisonTable };
