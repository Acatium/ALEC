/**
 * Experiment detail page
 */

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useExperiment, useExperimentResults } from '@/hooks/queries/useExperiments';
import {
  useStartExperiment,
  useStopExperiment,
  useDeleteExperiment,
} from '@/hooks/mutations/useExperimentMutations';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ChevronLeftIcon } from '@/components/ui/Icons';
import { ProgressBar } from '@/components/evaluation/ProgressBar';
import { TaskResultsTable } from '@/components/evaluation/TaskResultsTable';
import { LearningCurveChart } from '@/components/evaluation/LearningCurveChart';
import { formatDate, cn } from '@/lib/utils';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  stopped: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
};

function EvaluationDetailPage() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const navigate = useNavigate();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { data: experiment, isLoading, error, refetch } = useExperiment(experimentId);
  const { data: results } = useExperimentResults(experimentId);

  const startMutation = useStartExperiment();
  const stopMutation = useStopExperiment();
  const deleteMutation = useDeleteExperiment();

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading experiment..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load experiment"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  if (!experiment) {
    return (
      <AppLayout>
        <Error
          title="Experiment not found"
          message="The requested experiment does not exist"
          fullPage
        />
      </AppLayout>
    );
  }

  const progress =
    experiment.tasks_total > 0
      ? (experiment.tasks_completed / experiment.tasks_total) * 100
      : 0;

  const handleStart = async () => {
    await startMutation.mutateAsync(experiment.id);
  };

  const handleStop = async () => {
    await stopMutation.mutateAsync(experiment.id);
  };

  const handleDelete = async () => {
    await deleteMutation.mutateAsync(experiment.id);
    navigate('/evaluation');
  };

  // Build learning curve data - simple representation from results
  // Note: For real learning curves, we'd need checkpoint data from the API
  const learningCurveData = experiment.tasks_completed > 0
    ? [{
        epoch: 1,
        success_rate: experiment.success_rate ?? 0,
        tasks_completed: experiment.tasks_completed,
        label: experiment.name,
      }]
    : [];

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Back link */}
        <Link to="/evaluation">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeftIcon className="h-4 w-4" />
            Back to Experiments
          </Button>
        </Link>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{experiment.name}</h1>
              <Badge className={STATUS_COLORS[experiment.status] || STATUS_COLORS.pending}>
                {experiment.status}
              </Badge>
            </div>
            <p className="mt-1 text-gray-500 dark:text-gray-400">
              {experiment.experiment_type} · {experiment.dataset_split}
            </p>
          </div>
          <div className="flex gap-2">
            {experiment.status === 'pending' && (
              <Button onClick={handleStart} loading={startMutation.isPending}>
                Start Experiment
              </Button>
            )}
            {experiment.status === 'running' && (
              <Button variant="secondary" onClick={handleStop} loading={stopMutation.isPending}>
                Stop
              </Button>
            )}
            {experiment.status !== 'running' && (
              <Button variant="destructive" onClick={() => setShowDeleteDialog(true)}>
                Delete
              </Button>
            )}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Progress card */}
            <Card>
              <CardHeader>
                <CardTitle>Progress</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between text-sm">
                  <span>Tasks Completed</span>
                  <span>
                    {experiment.tasks_completed} / {experiment.tasks_total}
                  </span>
                </div>
                <ProgressBar
                  value={progress}
                  variant={
                    experiment.status === 'completed'
                      ? 'success'
                      : experiment.status === 'failed'
                        ? 'error'
                        : 'default'
                  }
                />
                {experiment.status === 'running' && (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Experiment is running...
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Learning curve chart */}
            {learningCurveData.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Learning Curve</CardTitle>
                </CardHeader>
                <CardContent>
                  <LearningCurveChart data={learningCurveData} height={250} />
                </CardContent>
              </Card>
            )}

            {/* Task results */}
            <Card>
              <CardHeader>
                <CardTitle>Task Results</CardTitle>
              </CardHeader>
              <CardContent>
                <TaskResultsTable results={results?.task_results ?? []} />
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Stats card */}
            <Card>
              <CardHeader>
                <CardTitle>Statistics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center">
                  <span
                    className={cn(
                      'text-4xl font-bold',
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
                  <p className="text-sm text-gray-500">Task Success %</p>
                </div>
                <div className="text-center border-t border-gray-200 dark:border-gray-700 pt-4">
                  <span
                    className={cn(
                      'text-3xl font-bold',
                      experiment.total_assertions > 0 && (experiment.passed_assertions / experiment.total_assertions) >= 0.7
                        ? 'text-blue-600 dark:text-blue-400'
                        : experiment.total_assertions > 0 && (experiment.passed_assertions / experiment.total_assertions) >= 0.5
                          ? 'text-yellow-600 dark:text-yellow-400'
                          : 'text-red-600 dark:text-red-400'
                    )}
                  >
                    {experiment.total_assertions > 0
                      ? `${((experiment.passed_assertions / experiment.total_assertions) * 100).toFixed(1)}%`
                      : '-'}
                  </span>
                  <p className="text-sm text-gray-500">Assertion Pass %</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {experiment.passed_assertions} / {experiment.total_assertions} assertions
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-4 text-center text-sm border-t border-gray-200 dark:border-gray-700 pt-4">
                  <div>
                    <span className="block font-semibold text-green-600 dark:text-green-400">
                      {results?.task_results?.filter((r) => r.success === true).length ?? 0}
                    </span>
                    <span className="text-gray-500">Succeeded</span>
                  </div>
                  <div>
                    <span className="block font-semibold text-red-600 dark:text-red-400">
                      {results?.task_results?.filter((r) => r.success === false).length ?? 0}
                    </span>
                    <span className="text-gray-500">Failed</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Config card */}
            <Card>
              <CardHeader>
                <CardTitle>Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Dataset</span>
                  <span>{experiment.dataset_split}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Type</span>
                  <span>{experiment.experiment_type}</span>
                </div>
                {experiment.config && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Task Limit</span>
                      <span>{(experiment.config as Record<string, unknown>).task_limit as number || 'All'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Turns/Task</span>
                      <span>{(experiment.config as Record<string, unknown>).turns_per_task as number || 20}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Checkpoint</span>
                      <span>{(experiment.config as Record<string, unknown>).checkpoint_interval as number || 10}</span>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Metadata card */}
            <Card>
              <CardHeader>
                <CardTitle>Metadata</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Created</span>
                  <span>{formatDate(experiment.created_at)}</span>
                </div>
                {experiment.started_at && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Started</span>
                    <span>{formatDate(experiment.started_at)}</span>
                  </div>
                )}
                {experiment.completed_at && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Completed</span>
                    <span>{formatDate(experiment.completed_at)}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-gray-500">ID</span>
                  <span className="font-mono text-xs">{experiment.id.slice(0, 8)}...</span>
                </div>
              </CardContent>
            </Card>
            </div>
          </div>
        </div>
      </PageContainer>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={showDeleteDialog}
        onClose={() => setShowDeleteDialog(false)}
        onConfirm={handleDelete}
        title="Delete Experiment?"
        description="This will permanently delete the experiment and all its results. This action cannot be undone."
        confirmText="Delete"
        variant="destructive"
        loading={deleteMutation.isPending}
      />
    </AppLayout>
  );
}

export default EvaluationDetailPage;
