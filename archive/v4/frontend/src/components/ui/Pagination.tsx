/**
 * Pagination component
 */

import { cn } from '@/lib/utils';
import { Button } from './Button';

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  pageSizeOptions?: number[];
  className?: string;
}

function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100],
  className,
}: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  const startItem = (page - 1) * pageSize + 1;
  const endItem = Math.min(page * pageSize, total);

  const canGoPrev = page > 1;
  const canGoNext = page < totalPages;

  return (
    <div className={cn('flex items-center justify-between', className)}>
      <div className="text-sm text-gray-500 dark:text-gray-400">
        Showing {startItem} to {endItem} of {total} results
      </div>

      <div className="flex items-center gap-4">
        {onPageSizeChange && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Per page:</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-8 rounded border border-gray-300 bg-transparent px-2 text-sm dark:border-gray-700"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(1)}
            disabled={!canGoPrev}
            aria-label="First page"
          >
            &laquo;
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={!canGoPrev}
            aria-label="Previous page"
          >
            &lsaquo;
          </Button>

          <span className="px-3 text-sm">
            Page {page} of {totalPages}
          </span>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={!canGoNext}
            aria-label="Next page"
          >
            &rsaquo;
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(totalPages)}
            disabled={!canGoNext}
            aria-label="Last page"
          >
            &raquo;
          </Button>
        </div>
      </div>
    </div>
  );
}

export { Pagination };
