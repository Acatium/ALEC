/**
 * Sessions list page
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useSessions } from '@/hooks/queries/useSessions';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { EmptyState } from '@/components/shared/EmptyState';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/Table';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Pagination } from '@/components/ui/Pagination';
import { MessageSquareIcon } from '@/components/ui/Icons';
import { formatRelativeTime } from '@/lib/utils';
import { DEBOUNCE_SEARCH, DEFAULT_PAGE_SIZE } from '@/lib/constants';
import { debounce } from '@/lib/utils';

function SessionsPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [domain, setDomain] = useState('');

  const { data, isLoading, error, refetch } = useSessions({
    domain: domain || undefined,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });

  const handleDomainChange = debounce((value: string) => {
    setDomain(value);
    setPage(1);
  }, DEBOUNCE_SEARCH);

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading sessions..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load sessions"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  const sessions = data?.sessions ?? [];
  const total = data?.total ?? 0;

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Sessions</h1>
          <p className="text-gray-500 dark:text-gray-400">
            View and manage chat sessions
          </p>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="flex flex-wrap gap-4 p-4">
            <div className="flex-1">
              <Input
                placeholder="Filter by domain..."
                defaultValue={domain}
                onChange={(e) => handleDomainChange(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        {sessions.length === 0 ? (
          <EmptyState
            icon={<MessageSquareIcon className="h-12 w-12" />}
            title="No sessions found"
            description="No sessions match your filters"
            action={{
              label: 'Clear filters',
              onClick: () => {
                setDomain('');
                setPage(1);
              },
            }}
          />
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session ID</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Turns</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Outcomes</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((session) => (
                  <TableRow key={session.session_id}>
                    <TableCell className="font-mono text-sm">
                      <Link
                        to={`/sessions/${session.session_id}`}
                        className="text-blue-600 hover:text-blue-800 hover:underline dark:text-blue-400 dark:hover:text-blue-300"
                      >
                        {session.session_id.slice(0, 8)}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm text-gray-600 dark:text-gray-400">
                      {session.domain}
                    </TableCell>
                    <TableCell className="text-sm">{session.message_count}</TableCell>
                    <TableCell className="text-sm">
                      {session.duration_ms != null
                        ? `${(session.duration_ms / 1000).toFixed(1)}s`
                        : '-'}
                    </TableCell>
                    <TableCell className="text-xs">
                      {session.micro_outcomes ? (
                        <span className="flex flex-wrap gap-1">
                          {session.micro_outcomes.solved > 0 && (
                            <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 px-1.5 py-0">
                              {session.micro_outcomes.solved} solved
                            </Badge>
                          )}
                          {session.micro_outcomes.progress > 0 && (
                            <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-1.5 py-0">
                              {session.micro_outcomes.progress} progress
                            </Badge>
                          )}
                          {session.micro_outcomes.stuck > 0 && (
                            <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300 px-1.5 py-0">
                              {session.micro_outcomes.stuck} stuck
                            </Badge>
                          )}
                          {session.micro_outcomes.error > 0 && (
                            <Badge className="bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 px-1.5 py-0">
                              {session.micro_outcomes.error} error
                            </Badge>
                          )}
                          {session.micro_outcomes.solved === 0 &&
                           session.micro_outcomes.progress === 0 &&
                           session.micro_outcomes.stuck === 0 &&
                           session.micro_outcomes.error === 0 && (
                            <span className="text-gray-400">no data</span>
                          )}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500 dark:text-gray-400">
                      {formatRelativeTime(session.created_at)}
                    </TableCell>
                  </TableRow>
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

export default SessionsPage;
