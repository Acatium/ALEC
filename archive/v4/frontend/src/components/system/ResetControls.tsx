/**
 * Reset controls component
 */

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import {
  useResetAll,
  useResetSessions,
  useResetCounters,
  useResetEvaluations,
  useResetRedis,
  useResetBullets,
} from '@/hooks/mutations/useSystemMutations';

export interface ResetControlsProps {
  className?: string;
}

type ResetType = 'all' | 'sessions' | 'counters' | 'evaluations' | 'redis' | 'bullets';

const RESET_OPTIONS: {
  type: ResetType;
  label: string;
  description: string;
  variant: 'destructive' | 'secondary';
}[] = [
  {
    type: 'sessions',
    label: 'Reset Sessions',
    description: 'Clear all sessions and events. Bullets are preserved.',
    variant: 'secondary',
  },
  {
    type: 'counters',
    label: 'Reset Counters',
    description: 'Reset bullet effectiveness counters to zero.',
    variant: 'secondary',
  },
  {
    type: 'evaluations',
    label: 'Reset Evaluations',
    description: 'Clear all evaluation experiments and results.',
    variant: 'secondary',
  },
  {
    type: 'redis',
    label: 'Flush Redis',
    description: 'Clear Redis cache (session bullets, etc.).',
    variant: 'secondary',
  },
  {
    type: 'bullets',
    label: 'Delete Bullets',
    description: 'Permanently delete ALL bullets. This cannot be undone!',
    variant: 'destructive',
  },
  {
    type: 'all',
    label: 'Reset Everything',
    description: 'Reset all learning data: sessions, counters, evaluations, Redis.',
    variant: 'destructive',
  },
];

function ResetControls({ className }: ResetControlsProps) {
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    type: ResetType;
    label: string;
    description: string;
  }>({ open: false, type: 'sessions', label: '', description: '' });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const resetAllMutation = useResetAll();
  const resetSessionsMutation = useResetSessions();
  const resetCountersMutation = useResetCounters();
  const resetEvaluationsMutation = useResetEvaluations();
  const resetRedisMutation = useResetRedis();
  const resetBulletsMutation = useResetBullets();

  // Auto-dismiss success message after 3 seconds
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  const handleReset = async () => {
    const { type, label } = confirmDialog;
    setError(null);
    setSuccess(null);

    try {
      switch (type) {
        case 'all':
          await resetAllMutation.mutateAsync();
          break;
        case 'sessions':
          await resetSessionsMutation.mutateAsync();
          break;
        case 'counters':
          await resetCountersMutation.mutateAsync();
          break;
        case 'evaluations':
          await resetEvaluationsMutation.mutateAsync();
          break;
        case 'redis':
          await resetRedisMutation.mutateAsync();
          break;
        case 'bullets':
          await resetBulletsMutation.mutateAsync();
          break;
      }
      setSuccess(`${label} completed successfully`);
      setConfirmDialog((prev) => ({ ...prev, open: false }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Reset failed';
      setError(message);
      setConfirmDialog((prev) => ({ ...prev, open: false }));
    }
  };

  const isLoading =
    resetAllMutation.isPending ||
    resetSessionsMutation.isPending ||
    resetCountersMutation.isPending ||
    resetEvaluationsMutation.isPending ||
    resetRedisMutation.isPending ||
    resetBulletsMutation.isPending;

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Reset Controls</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Success message */}
        {success && (
          <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400">
            {success}
          </div>
        )}
        {/* Error message */}
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            <strong>Error:</strong> {error}
          </div>
        )}
        <div className="space-y-4">
          {RESET_OPTIONS.map((option) => (
            <div
              key={option.type}
              className="flex items-center justify-between gap-4 rounded-lg border border-gray-200 p-4 dark:border-gray-700"
            >
              <div>
                <span className="font-medium">{option.label}</span>
                <p className="text-sm text-gray-500 dark:text-gray-400">{option.description}</p>
              </div>
              <Button
                variant={option.variant}
                size="sm"
                onClick={() =>
                  setConfirmDialog({
                    open: true,
                    type: option.type,
                    label: option.label,
                    description: option.description,
                  })
                }
                disabled={isLoading}
              >
                Reset
              </Button>
            </div>
          ))}
        </div>
      </CardContent>

      <ConfirmDialog
        open={confirmDialog.open}
        onClose={() => setConfirmDialog((prev) => ({ ...prev, open: false }))}
        onConfirm={handleReset}
        title={`${confirmDialog.label}?`}
        description={`${confirmDialog.description} This action cannot be undone.`}
        confirmText="Reset"
        variant="destructive"
        loading={isLoading}
      />
    </Card>
  );
}

export { ResetControls };
