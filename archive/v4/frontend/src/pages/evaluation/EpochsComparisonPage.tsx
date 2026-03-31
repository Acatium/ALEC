/**
 * Multi-epoch comparison page
 */

import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useEpochsComparison } from '@/hooks/queries/useExperiments';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { EmptyState } from '@/components/shared/EmptyState';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ChevronLeftIcon, BeakerIcon } from '@/components/ui/Icons';
import { LearningCurveChart } from '@/components/evaluation/LearningCurveChart';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/Table';
import { cn } from '@/lib/utils';

function EpochsComparisonPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [inputIds, setInputIds] = useState('');

  // Get experiment IDs from URL
  const experimentIds = searchParams.get('experiment_ids')?.split(',').filter(Boolean) ?? [];

  const { data, isLoading, error, refetch } = useEpochsComparison(
    experimentIds.length > 0 ? experimentIds : undefined
  );

  useEffect(() => {
    setInputIds(experimentIds.join(', '));
  }, [searchParams]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const ids = inputIds
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length > 0) {
      setSearchParams({ experiment_ids: ids.join(',') });
    }
  };

  const handleClear = () => {
    setInputIds('');
    setSearchParams({});
  };

  // Build learning curve data from epochs
  const learningCurveData =
    data?.epochs?.map((epoch, idx) => ({
      epoch: idx + 1,
      success_rate: epoch.success_rate ?? 0,
      tasks_completed: epoch.tasks_completed,
      label: epoch.name,
    })) ?? [];

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
          <div>
            <h1 className="text-2xl font-bold">Epochs Comparison</h1>
          <p className="text-gray-500 dark:text-gray-400">
            Compare performance across multiple experiment epochs
          </p>
        </div>

        {/* Input form */}
        <Card>
          <CardHeader>
            <CardTitle>Experiment IDs</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex gap-4">
              <div className="flex-1">
                <Input
                  placeholder="Enter experiment IDs (comma-separated)"
                  value={inputIds}
                  onChange={(e) => setInputIds(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={!inputIds.trim()}>
                Compare
              </Button>
              {experimentIds.length > 0 && (
                <Button type="button" variant="ghost" onClick={handleClear}>
                  Clear
                </Button>
              )}
            </form>
          </CardContent>
        </Card>

        {/* Content */}
        {isLoading ? (
          <Loading text="Loading epochs data..." />
        ) : error ? (
          <Error
            title="Failed to load epochs"
            message={error.message}
            onRetry={() => refetch()}
          />
        ) : experimentIds.length === 0 ? (
          <EmptyState
            icon={<BeakerIcon className="h-12 w-12" />}
            title="Enter experiment IDs"
            description="Enter the IDs of experiments you want to compare"
          />
        ) : !data?.epochs || data.epochs.length === 0 ? (
          <EmptyState
            icon={<BeakerIcon className="h-12 w-12" />}
            title="No epochs found"
            description="No epoch data found for the specified experiments"
          />
        ) : (
          <>
            {/* Learning curve */}
            <Card>
              <CardHeader>
                <CardTitle>Learning Curve Across Epochs</CardTitle>
              </CardHeader>
              <CardContent>
                <LearningCurveChart data={learningCurveData} height={350} />
              </CardContent>
            </Card>

            {/* Epochs table */}
            <Card>
              <CardHeader>
                <CardTitle>Epoch Details</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Epoch</TableHead>
                      <TableHead>Experiment</TableHead>
                      <TableHead>Tasks</TableHead>
                      <TableHead>Success Rate</TableHead>
                      <TableHead>Change</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.epochs.map((epoch, idx) => {
                      const prevRate = idx > 0 ? data.epochs[idx - 1].success_rate : null;
                      const epochRate = epoch.success_rate ?? 0;
                      const change =
                        prevRate != null ? epochRate - prevRate : null;

                      return (
                        <TableRow key={epoch.id}>
                          <TableCell className="font-semibold">{idx + 1}</TableCell>
                          <TableCell>
                            <Link
                              to={`/evaluation/${epoch.id}`}
                              className="text-blue-600 hover:underline dark:text-blue-400"
                            >
                              {epoch.name}
                            </Link>
                          </TableCell>
                          <TableCell>{epoch.tasks_completed}</TableCell>
                          <TableCell>
                            <span
                              className={cn(
                                'font-semibold',
                                epochRate >= 0.7
                                  ? 'text-green-600 dark:text-green-400'
                                  : epochRate >= 0.5
                                    ? 'text-yellow-600 dark:text-yellow-400'
                                    : 'text-red-600 dark:text-red-400'
                              )}
                            >
                              {(epochRate * 100).toFixed(1)}%
                            </span>
                          </TableCell>
                          <TableCell>
                            {change != null ? (
                              <span
                                className={cn(
                                  'font-semibold',
                                  change > 0
                                    ? 'text-green-600 dark:text-green-400'
                                    : change < 0
                                      ? 'text-red-600 dark:text-red-400'
                                      : 'text-gray-500'
                                )}
                              >
                                {change > 0 ? '+' : ''}
                                {(change * 100).toFixed(1)}%
                              </span>
                            ) : (
                              '-'
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Summary */}
            <Card>
              <CardHeader>
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
                  <div className="text-center">
                    <span className="block text-2xl font-bold text-blue-600 dark:text-blue-400">
                      {data.epochs.length}
                    </span>
                    <span className="text-sm text-gray-500">Epochs</span>
                  </div>
                  <div className="text-center">
                    <span className="block text-2xl font-bold text-green-600 dark:text-green-400">
                      {(Math.max(...data.epochs.map((e) => e.success_rate ?? 0)) * 100).toFixed(1)}%
                    </span>
                    <span className="text-sm text-gray-500">Best Rate</span>
                  </div>
                  <div className="text-center">
                    <span className="block text-2xl font-bold">
                      {((data.epochs[data.epochs.length - 1]?.success_rate ?? 0) * 100).toFixed(1)}%
                    </span>
                    <span className="text-sm text-gray-500">Latest Rate</span>
                  </div>
                  <div className="text-center">
                    {(() => {
                      const latestRate = data.epochs[data.epochs.length - 1]?.success_rate ?? 0;
                      const firstRate = data.epochs[0]?.success_rate ?? 0;
                      const improvement = latestRate - firstRate;
                      return (
                        <>
                          <span
                            className={cn(
                              'block text-2xl font-bold',
                              improvement > 0
                                ? 'text-green-600 dark:text-green-400'
                                : improvement < 0
                                  ? 'text-red-600 dark:text-red-400'
                                  : ''
                            )}
                          >
                            {improvement > 0 ? '+' : ''}
                            {(improvement * 100).toFixed(1)}%
                          </span>
                          <span className="text-sm text-gray-500">Total Change</span>
                        </>
                      );
                    })()}
                  </div>
                </div>
              </CardContent>
            </Card>
            </>
          )}
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default EpochsComparisonPage;
