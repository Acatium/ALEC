/**
 * Create new experiment page (v2 - Full functionality)
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useCreateExperiment } from '@/hooks/mutations/useExperimentMutations';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { ChevronLeftIcon } from '@/components/ui/Icons';
import { Link } from 'react-router-dom';
import type { ExperimentCreate } from '@/api/types';

const DATASET_SPLIT_OPTIONS = [
  { value: 'test_normal', label: 'Test Normal' },
  { value: 'test_challenge', label: 'Test Challenge' },
  { value: 'train', label: 'Train' },
  { value: 'dev', label: 'Dev' },
];

const EXPERIMENT_TYPES = [
  { value: 'baseline', label: 'Baseline' },
  { value: 'learning_curve', label: 'Learning Curve' },
  { value: 'bullet_evolution', label: 'Bullet Evolution' },
];

function EvaluationNewPage() {
  const navigate = useNavigate();
  const createMutation = useCreateExperiment();

  const [formData, setFormData] = useState<ExperimentCreate>({
    name: '',
    experiment_type: 'baseline',
    dataset_split: 'test_normal',
    task_limit: undefined,
    checkpoint_interval: 10,
    turns_per_task: 20,
  });

  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const experiment = await createMutation.mutateAsync(formData);
      navigate(`/evaluation/${experiment.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create experiment';
      setError(message);
      console.error('Create experiment failed:', err);
    }
  };

  return (
    <AppLayout>
      <PageContainer>
        <div className="mx-auto max-w-2xl space-y-6">
        {/* Back link */}
        <Link to="/evaluation">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeftIcon className="h-4 w-4" />
            Back to Experiments
          </Button>
        </Link>

        <Card>
          <form onSubmit={handleSubmit}>
            <CardHeader>
              <CardTitle>Create Experiment</CardTitle>
            </CardHeader>

            <CardContent className="space-y-6">
              {/* Error display */}
              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                  <strong>Error:</strong> {error}
                </div>
              )}
              {/* Basic info */}
              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Name</label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Baseline Evaluation 2025-01"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium">Dataset Split</label>
                    <Select
                      options={DATASET_SPLIT_OPTIONS}
                      value={formData.dataset_split}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, dataset_split: e.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium">Experiment Type</label>
                    <Select
                      options={EXPERIMENT_TYPES}
                      value={formData.experiment_type}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, experiment_type: e.target.value }))
                      }
                    />
                  </div>
                </div>
              </div>

              {/* Advanced options */}
              <div className="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Advanced Options</div>
                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Task Limit
                  </label>
                  <Input
                    type="number"
                    value={formData.task_limit ?? ''}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        task_limit: e.target.value ? parseInt(e.target.value) : undefined,
                      }))
                    }
                    placeholder="Leave empty for all tasks"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Maximum number of tasks to run (empty = all)
                  </p>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Turns Per Task ({formData.turns_per_task || 20})
                  </label>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    value={formData.turns_per_task || 20}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        turns_per_task: parseInt(e.target.value),
                      }))
                    }
                    className="w-full"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium">
                    Checkpoint Interval ({formData.checkpoint_interval || 10})
                  </label>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    step="5"
                    value={formData.checkpoint_interval || 10}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        checkpoint_interval: parseInt(e.target.value),
                      }))
                    }
                    className="w-full"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Tasks between progress checkpoints
                  </p>
                </div>
              </div>
            </CardContent>

            <CardFooter className="gap-2">
              <Link to="/evaluation" className="flex-1">
                <Button variant="secondary" className="w-full" type="button">
                  Cancel
                </Button>
              </Link>
              <Button
                type="submit"
                className="flex-1"
                loading={createMutation.isPending}
                disabled={!formData.name.trim()}
              >
                Create Experiment
              </Button>
            </CardFooter>
          </form>
        </Card>
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default EvaluationNewPage;
