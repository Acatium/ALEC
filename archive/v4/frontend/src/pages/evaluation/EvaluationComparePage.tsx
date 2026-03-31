/**
 * Experiment comparison page
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useExperiments } from '@/hooks/queries/useExperiments';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { EmptyState } from '@/components/shared/EmptyState';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ChevronLeftIcon, BeakerIcon } from '@/components/ui/Icons';
import { ComparisonTable } from '@/components/evaluation/ComparisonTable';
import { LearningCurveChart, type LearningCurveDataPoint } from '@/components/evaluation/LearningCurveChart';

function EvaluationComparePage() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { data: experiments, isLoading, error, refetch } = useExperiments();

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading experiments..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load experiments"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  const experimentsList = experiments?.experiments ?? [];
  const completedExperiments = experimentsList.filter((e) => e.status === 'completed');
  const selectedExperiments = completedExperiments.filter((e) => selectedIds.has(e.id));

  const handleToggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === completedExperiments.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(completedExperiments.map((e: (typeof completedExperiments)[number]) => e.id)));
    }
  };

  // Build combined learning curve data
  type Experiment = (typeof completedExperiments)[number];
  const learningCurveData: LearningCurveDataPoint[] = selectedExperiments
    .sort((a: Experiment, b: Experiment) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .map((exp: Experiment, idx: number) => ({
      epoch: idx + 1,
      success_rate: exp.success_rate ?? 0,
      tasks_completed: exp.tasks_completed,
      label: exp.name,
    }));

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
            <h1 className="text-2xl font-bold">Compare Experiments</h1>
          <p className="text-gray-500 dark:text-gray-400">
            Select completed experiments to compare their performance
          </p>
        </div>

        {completedExperiments.length === 0 ? (
          <EmptyState
            icon={<BeakerIcon className="h-12 w-12" />}
            title="No completed experiments"
            description="Complete some experiments to compare them"
            action={{ label: 'View Experiments', onClick: () => window.location.href = '/evaluation' }}
          />
        ) : (
          <>
            {/* Selection */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Select Experiments</CardTitle>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={handleSelectAll}>
                      {selectedIds.size === completedExperiments.length
                        ? 'Deselect All'
                        : 'Select All'}
                    </Button>
                    <span className="text-sm text-gray-500">
                      {selectedIds.size} selected
                    </span>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {completedExperiments.map((exp: Experiment) => (
                    <label
                      key={exp.id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-gray-200 p-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(exp.id)}
                        onChange={() => handleToggle(exp.id)}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                      <div className="flex-1">
                        <span className="font-medium">{exp.name}</span>
                        <span className="ml-2 text-sm text-gray-500">
                          ({exp.dataset_split})
                        </span>
                      </div>
                      <span className="font-semibold">
                        {exp.success_rate != null
                          ? `${(exp.success_rate * 100).toFixed(1)}%`
                          : '-'}
                      </span>
                    </label>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Comparison */}
            {selectedExperiments.length > 0 && (
              <>
                {/* Learning curve */}
                {learningCurveData.length > 1 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Performance Over Time</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <LearningCurveChart data={learningCurveData} height={300} />
                    </CardContent>
                  </Card>
                )}

                {/* Comparison table */}
                <Card>
                  <CardHeader>
                    <CardTitle>Comparison Table</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ComparisonTable experiments={selectedExperiments} highlightBest />
                  </CardContent>
                </Card>

                {/* Summary stats */}
                <Card>
                  <CardHeader>
                    <CardTitle>Summary Statistics</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
                      <div className="text-center">
                        <span className="block text-2xl font-bold text-blue-600 dark:text-blue-400">
                          {selectedExperiments.length}
                        </span>
                        <span className="text-sm text-gray-500">Experiments</span>
                      </div>
                      <div className="text-center">
                        <span className="block text-2xl font-bold text-green-600 dark:text-green-400">
                          {Math.max(
                            ...selectedExperiments.map((e: Experiment) => (e.success_rate ?? 0) * 100)
                          ).toFixed(1)}
                          %
                        </span>
                        <span className="text-sm text-gray-500">Best Task Success %</span>
                      </div>
                      <div className="text-center">
                        <span className="block text-2xl font-bold">
                          {(
                            selectedExperiments.reduce(
                              (sum: number, e: Experiment) => sum + (e.success_rate ?? 0),
                              0
                            ) /
                            selectedExperiments.length *
                            100
                          ).toFixed(1)}
                          %
                        </span>
                        <span className="text-sm text-gray-500">Avg Task Success %</span>
                      </div>
                      <div className="text-center">
                        <span className="block text-2xl font-bold">
                          {selectedExperiments.reduce((sum: number, e: Experiment) => sum + e.tasks_completed, 0)}
                        </span>
                        <span className="text-sm text-gray-500">Total Tasks</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
            </>
          )}
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default EvaluationComparePage;
