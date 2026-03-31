/**
 * Bullets library page
 */

import { useState, useMemo } from 'react';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useBullets } from '@/hooks/queries/useBullets';
import { useBulkUpdateStatus } from '@/hooks/mutations/useUpdateBullet';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { EmptyState } from '@/components/shared/EmptyState';
import { Card, CardContent } from '@/components/ui/Card';
import { Table, TableHeader, TableBody, TableHead, TableRow } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Pagination } from '@/components/ui/Pagination';
import { BookOpenIcon } from '@/components/ui/Icons';
import { BulletFilters } from '@/components/library/BulletFilters';
import { BulletRow } from '@/components/library/BulletRow';
import { debounce } from '@/lib/utils';
import { DEBOUNCE_SEARCH, DEFAULT_PAGE_SIZE } from '@/lib/constants';
import type { BulletStatus } from '@/api/types';

function BulletsLibraryPage() {
  // Filters
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data, isLoading, error, refetch } = useBullets({
    page,
    page_size: pageSize,
    status: status as BulletStatus | undefined,
    search: debouncedSearch || undefined,
    sort_by: 'created_at',
    sort_order: 'desc',
  });

  const bulkUpdateMutation = useBulkUpdateStatus();

  // Debounced search
  const handleSearchChange = useMemo(
    () =>
      debounce((value: string) => {
        setDebouncedSearch(value);
        setPage(1);
      }, DEBOUNCE_SEARCH),
    []
  );

  const handleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (!data?.bullets) return;
    const allIds = data.bullets.map((b) => b.id);
    const allSelected = allIds.every((id) => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(allIds));
    }
  };

  const handleBulkAction = async (newStatus: BulletStatus) => {
    if (selectedIds.size === 0) return;
    await bulkUpdateMutation.mutateAsync({
      bulletIds: Array.from(selectedIds),
      status: newStatus,
    });
    setSelectedIds(new Set());
  };

  const handleClearFilters = () => {
    setStatus('');
    setSearch('');
    setDebouncedSearch('');
    setPage(1);
  };

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading bullets..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load bullets"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  const bullets = data?.bullets ?? [];
  const total = data?.total ?? 0;

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Bullet Library</h1>
          <p className="text-gray-500 dark:text-gray-400">
            Manage knowledge bullets ({total} total)
          </p>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="p-4">
            <BulletFilters
              status={status}
              search={search}
              onStatusChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
              onSearchChange={(v) => {
                setSearch(v);
                handleSearchChange(v);
              }}
              onClear={handleClearFilters}
            />
          </CardContent>
        </Card>

        {/* Bulk actions */}
        {selectedIds.size > 0 && (
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <span className="text-sm text-gray-500">{selectedIds.size} selected</span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleBulkAction('active')}
                loading={bulkUpdateMutation.isPending}
              >
                Activate
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleBulkAction('archived')}
                loading={bulkUpdateMutation.isPending}
              >
                Archive
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                Clear selection
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Table */}
        {bullets.length === 0 ? (
          <EmptyState
            icon={<BookOpenIcon className="h-12 w-12" />}
            title="No bullets found"
            description="No bullets match your filters"
            action={{
              label: 'Clear filters',
              onClick: handleClearFilters,
            }}
          />
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <input
                      type="checkbox"
                      checked={bullets.every((b) => selectedIds.has(b.id))}
                      onChange={handleSelectAll}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                  </TableHead>
                  <TableHead>Situation</TableHead>
                  <TableHead>Assertion</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Effectiveness</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bullets.map((bullet) => (
                  <BulletRow
                    key={bullet.id}
                    bullet={bullet}
                    selected={selectedIds.has(bullet.id)}
                    onSelect={handleSelect}
                  />
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            <div className="border-t border-gray-200 p-4 dark:border-gray-800">
              <Pagination
                page={page}
                pageSize={pageSize}
                total={total}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setPage(1);
                }}
              />
            </div>
          </Card>
          )}
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default BulletsLibraryPage;
