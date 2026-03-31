/**
 * AKU filters component (v4)
 */

import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { BULLET_STATUSES } from '@/lib/constants';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...BULLET_STATUSES.map((s) => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) })),
];

export interface BulletFiltersProps {
  status: string;
  search: string;
  onStatusChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onClear: () => void;
  className?: string;
}

function BulletFilters({
  status,
  search,
  onStatusChange,
  onSearchChange,
  onClear,
  className,
}: BulletFiltersProps) {
  const hasFilters = status || search;

  return (
    <div className={cn('flex flex-wrap items-center gap-4', className)}>
      {/* Status filter */}
      <div className="w-40">
        <Select
          options={STATUS_OPTIONS}
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
        />
      </div>

      {/* Search */}
      <div className="flex-1">
        <Input
          placeholder="Search AKUs..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>

      {/* Clear button */}
      {hasFilters && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

export { BulletFilters };
