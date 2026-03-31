/**
 * Loading component
 */

import { cn } from '@/lib/utils';
import { LoaderIcon } from '@/components/ui/Icons';

export interface LoadingProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
  className?: string;
  fullPage?: boolean;
}

function Loading({ size = 'md', text, className, fullPage = false }: LoadingProps) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  };

  const content = (
    <div className={cn('flex flex-col items-center justify-center gap-2', className)}>
      <LoaderIcon className={cn('text-blue-500', sizeClasses[size])} />
      {text && <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>}
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        {content}
      </div>
    );
  }

  return content;
}

export { Loading };
