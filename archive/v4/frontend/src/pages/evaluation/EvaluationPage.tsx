/**
 * Evaluation experiments list page
 */

import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useExperiments } from '@/hooks/queries/useExperiments';
import {
  useStartExperiment,
  useStopExperiment,
  useDeleteExperiment,
  useUpdateExperiment,
} from '@/hooks/mutations/useExperimentMutations';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { EmptyState } from '@/components/shared/EmptyState';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { BeakerIcon, PlusIcon } from '@/components/ui/Icons';
import { Badge } from '@/components/ui/Badge';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/Table';
import { EvaluationTrendsChart } from '@/components/evaluation/EvaluationTrendsChart';
import type { ExperimentSummary } from '@/api/types';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'stopped', label: 'Stopped' },
];

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  stopped: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
};

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={STATUS_COLORS[status] || STATUS_COLORS.pending}>
      {status}
    </Badge>
  );
}

interface EditableNameProps {
  id: string;
  name: string;
  onSave: (id: string, name: string) => void;
  isPending: boolean;
}

function EditableName({ id, name, onSave, isPending }: EditableNameProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSave = () => {
    if (editValue.trim() && editValue !== name) {
      onSave(id, editValue.trim());
    }
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    } else if (e.key === 'Escape') {
      setEditValue(name);
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        disabled={isPending}
        className="w-full rounded border border-blue-500 bg-white px-2 py-1 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800"
      />
    );
  }

  return (
    <div className="group flex items-center gap-1">
      <Link
        to={`/evaluation/${id}`}
        className="font-medium text-blue-600 hover:text-blue-800 hover:underline dark:text-blue-400 dark:hover:text-blue-300"
      >
        {name}
      </Link>
      <button
        onClick={() => setIsEditing(true)}
        className="ml-1 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        title="Edit name"
      >
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </button>
    </div>
  );
}

function EvaluationPage() {
  const [statusFilter, setStatusFilter] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: experiments, isLoading, error, refetch } = useExperiments();
  const startMutation = useStartExperiment();
  const stopMutation = useStopExperiment();
  const deleteMutation = useDeleteExperiment();
  const updateMutation = useUpdateExperiment();

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
  const filteredExperiments = statusFilter
    ? experimentsList.filter((e) => e.status === statusFilter)
    : experimentsList;

  const handleStart = async (id: string) => {
    await startMutation.mutateAsync(id);
  };

  const handleStop = async (id: string) => {
    await stopMutation.mutateAsync(id);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await deleteMutation.mutateAsync(deleteTarget);
    setDeleteTarget(null);
  };

  const handleRename = (id: string, name: string) => {
    updateMutation.mutate({ id, name });
  };

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Evaluation</h1>
            <p className="text-gray-500 dark:text-gray-400">
              Run and manage evaluation experiments
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/evaluation/compare">
              <Button variant="secondary">Compare Experiments</Button>
            </Link>
            <Link to="/evaluation/new">
              <Button className="gap-1">
                <PlusIcon className="h-4 w-4" />
                New Experiment
              </Button>
            </Link>
          </div>
        </div>

        {/* Learning Trends Chart */}
        <EvaluationTrendsChart experiments={experimentsList} />

        {/* Filters */}
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <div className="w-48">
              <Select
                options={STATUS_OPTIONS}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              />
            </div>
            {statusFilter && (
              <Button variant="ghost" size="sm" onClick={() => setStatusFilter('')}>
                Clear filter
              </Button>
            )}
            <div className="flex-1" />
            <span className="text-sm text-gray-500">
              {filteredExperiments?.length ?? 0} experiments
            </span>
          </CardContent>
        </Card>

        {/* Experiments table */}
        {!filteredExperiments || filteredExperiments.length === 0 ? (
          <EmptyState
            icon={<BeakerIcon className="h-12 w-12" />}
            title="No experiments found"
            description={
              statusFilter
                ? 'No experiments match your filter'
                : 'Create your first evaluation experiment'
            }
            action={
              statusFilter
                ? { label: 'Clear filter', onClick: () => setStatusFilter('') }
                : { label: 'Create Experiment', href: '/evaluation/new' }
            }
          />
        ) : (
          <Card>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Dataset</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Progress</TableHead>
                    <TableHead>Task Success %</TableHead>
                    <TableHead>Assertion Pass</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="w-[120px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredExperiments.map((experiment: ExperimentSummary) => (
                    <TableRow key={experiment.id}>
                      <TableCell>
                        <EditableName
                          id={experiment.id}
                          name={experiment.name}
                          onSave={handleRename}
                          isPending={updateMutation.isPending}
                        />
                      </TableCell>
                      <TableCell className="text-sm text-gray-600 dark:text-gray-400">
                        {experiment.experiment_type}
                      </TableCell>
                      <TableCell className="text-sm text-gray-600 dark:text-gray-400">
                        {experiment.dataset_split}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={experiment.status} />
                      </TableCell>
                      <TableCell className="text-sm">
                        {experiment.tasks_completed}/{experiment.tasks_total || '?'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {experiment.success_rate != null
                          ? `${(experiment.success_rate * 100).toFixed(1)}%`
                          : '-'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {experiment.total_assertions > 0
                          ? `${((experiment.passed_assertions / experiment.total_assertions) * 100).toFixed(1)}%`
                          : '-'}
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">
                        {new Date(experiment.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {experiment.status === 'pending' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleStart(experiment.id)}
                              disabled={startMutation.isPending}
                            >
                              Start
                            </Button>
                          )}
                          {experiment.status === 'running' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleStop(experiment.id)}
                              disabled={stopMutation.isPending}
                            >
                              Stop
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTarget(experiment.id)}
                            className="text-red-600 hover:text-red-700 dark:text-red-400"
                          >
                            Delete
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
          )}
        </div>
      </PageContainer>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
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

export default EvaluationPage;
