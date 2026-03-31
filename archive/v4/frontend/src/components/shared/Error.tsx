/**
 * Error display component
 */

import { cn } from '@/lib/utils';
import { AlertCircleIcon } from '@/components/ui/Icons';
import { Button } from '@/components/ui/Button';

export interface ErrorProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
  fullPage?: boolean;
}

function Error({
  title = 'Something went wrong',
  message = 'An error occurred while loading. Please try again.',
  onRetry,
  className,
  fullPage = false,
}: ErrorProps) {
  const content = (
    <div className={cn('flex flex-col items-center justify-center gap-4 text-center', className)}>
      <AlertCircleIcon className="h-12 w-12 text-red-500" />
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{message}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex min-h-[400px] items-center justify-center p-8">
        {content}
      </div>
    );
  }

  return content;
}

export { Error };
