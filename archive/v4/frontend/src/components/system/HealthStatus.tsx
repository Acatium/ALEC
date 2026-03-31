/**
 * Health status component
 */

import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

export interface HealthStatusProps {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  label?: string;
  showLabel?: boolean;
  className?: string;
}

const STATUS_CONFIG = {
  healthy: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    dot: 'bg-green-500',
    label: 'Healthy',
  },
  degraded: {
    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    dot: 'bg-yellow-500',
    label: 'Degraded',
  },
  unhealthy: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    dot: 'bg-red-500',
    label: 'Unhealthy',
  },
  unknown: {
    color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
    dot: 'bg-gray-500',
    label: 'Unknown',
  },
};

function HealthStatus({ status, label, showLabel = true, className }: HealthStatusProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.unknown;

  return (
    <Badge className={cn('gap-1.5', config.color, className)}>
      <span className={cn('h-2 w-2 rounded-full', config.dot)} />
      {showLabel && (label || config.label)}
    </Badge>
  );
}

export { HealthStatus };
