/**
 * Experiment card component (v2 - Full functionality)
 */

import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ProgressBar } from './ProgressBar';
import { formatDate, cn } from '@/lib/utils';
import type { ExperimentSummary } from '@/api/types';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  stopped: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
};

export interface ExperimentCardProps {
  experiment: ExperimentSummary;
  onStart?: (id: string) => void;
  onStop?: (id: string) => void;
  onDelete?: (id: string) => void;
  loading?: boolean;
  className?: string;
}

function ExperimentCard({
  experiment,
  onStart,
  onStop,
  onDelete,
  loading,
  className,
}: ExperimentCardProps) {
  const progress =
    experiment.tasks_total > 0
      ? (experiment.tasks_completed / experiment.tasks_total) * 100
      : 0;

  const canStart = experiment.status === 'pending';
  const canStop = experiment.status === 'running';
  const canDelete = experiment.status !== 'running';

  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link to={`/evaluation/${experiment.id}`} className="hover:underline">
            <CardTitle className="text-lg">{experiment.name}</CardTitle>
          </Link>
          <Badge className={STATUS_COLORS[experiment.status] || STATUS_COLORS.pending}>
            {experiment.status}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {experiment.experiment_type} · {experiment.dataset_split}
        </p>
      </CardHeader>

      <CardContent className="flex-1 space-y-4">
        {/* Progress */}
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span>Progress</span>
            <span>
              {experiment.tasks_completed} / {experiment.tasks_total} tasks
            </span>
          </div>
          <ProgressBar value={progress} />
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500 dark:text-gray-400">Task Success %</span>
            <p className="font-semibold">
              {experiment.success_rate != null
                ? `${(experiment.success_rate * 100).toFixed(1)}%`
                : '-'}
            </p>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Assertions</span>
            <p className="font-semibold">
              {experiment.total_assertions > 0
                ? `${experiment.passed_assertions}/${experiment.total_assertions}`
                : '-'}
            </p>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Created</span>
            <p className="font-semibold">{formatDate(experiment.created_at)}</p>
          </div>
        </div>
      </CardContent>

      <CardFooter className="gap-2">
        <Link to={`/evaluation/${experiment.id}`} className="flex-1">
          <Button variant="secondary" className="w-full">
            View Details
          </Button>
        </Link>
        {canStart && onStart && (
          <Button onClick={() => onStart(experiment.id)} loading={loading}>
            Start
          </Button>
        )}
        {canStop && onStop && (
          <Button variant="secondary" onClick={() => onStop(experiment.id)} loading={loading}>
            Stop
          </Button>
        )}
        {canDelete && onDelete && (
          <Button variant="destructive" onClick={() => onDelete(experiment.id)} loading={loading}>
            Delete
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

export { ExperimentCard };
