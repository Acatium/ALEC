/**
 * Empty state component
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
  className?: string;
}

function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex min-h-[300px] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-gray-300 p-8 text-center dark:border-gray-700',
        className
      )}
    >
      {icon && <div className="text-gray-400 dark:text-gray-500">{icon}</div>}
      <div>
        <h3 className="text-lg font-medium">{title}</h3>
        {description && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
      {action && (
        action.href ? (
          <a href={action.href}>
            <Button variant="primary">
              {action.label}
            </Button>
          </a>
        ) : (
          <Button variant="primary" onClick={action.onClick}>
            {action.label}
          </Button>
        )
      )}
    </div>
  );
}

export { EmptyState };
