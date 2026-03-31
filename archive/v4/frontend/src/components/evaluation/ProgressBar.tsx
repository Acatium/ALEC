/**
 * Progress bar component
 */

import { cn } from '@/lib/utils';

export interface ProgressBarProps {
  value: number;
  max?: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'success' | 'warning' | 'error';
  className?: string;
}

const SIZE_CLASSES = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
};

const VARIANT_CLASSES = {
  default: 'bg-blue-500 dark:bg-blue-400',
  success: 'bg-green-500 dark:bg-green-400',
  warning: 'bg-yellow-500 dark:bg-yellow-400',
  error: 'bg-red-500 dark:bg-red-400',
};

function ProgressBar({
  value,
  max = 100,
  showLabel = false,
  size = 'md',
  variant = 'default',
  className,
}: ProgressBarProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className={cn('w-full', className)}>
      <div
        className={cn(
          'w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700',
          SIZE_CLASSES[size]
        )}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all duration-300',
            VARIANT_CLASSES[variant]
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <div className="mt-1 text-right text-xs text-gray-500 dark:text-gray-400">
          {percentage.toFixed(0)}%
        </div>
      )}
    </div>
  );
}

export { ProgressBar };
