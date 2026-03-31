/**
 * Knowledge graph page - displays problem clusters and their relationships
 */

import { useState } from 'react';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useGraphHealth, useClusters } from '@/hooks/queries/useSystem';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';

function KnowledgeGraphPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const {
    data: graphHealth,
    isLoading: healthLoading,
    error: healthError,
  } = useGraphHealth();

  const {
    data: clusterData,
    isLoading: clustersLoading,
    error: clustersError,
    refetch,
  } = useClusters({ page, page_size: pageSize });

  const isLoading = healthLoading || clustersLoading;
  const error = healthError || clustersError;

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading knowledge graph..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load knowledge graph"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  const clusters = clusterData?.clusters ?? [];
  const totalClusters = clusterData?.total ?? 0;
  const totalPages = Math.ceil(totalClusters / pageSize);

  const filteredClusters = search
    ? clusters.filter((c) => c.label.toLowerCase().includes(search.toLowerCase()))
    : clusters;

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-2xl font-bold">Knowledge Graph</h1>
            <p className="text-gray-500 dark:text-gray-400">
              Problem clusters and their relationships
            </p>
          </div>

          {/* Stats overview */}
          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <span className="block text-2xl font-bold text-purple-600 dark:text-purple-400">
                    {graphHealth?.active_clusters ?? 0}
                  </span>
                  <span className="text-sm text-gray-500">Clusters</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <span className="block text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {graphHealth?.total_edges ?? 0}
                  </span>
                  <span className="text-sm text-gray-500">Total Edges</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <span className="block text-2xl font-bold text-green-600 dark:text-green-400">
                    {graphHealth?.solved_by_edges ?? 0}
                  </span>
                  <span className="text-sm text-gray-500">solved_by</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <span className="block text-2xl font-bold text-red-600 dark:text-red-400">
                    {graphHealth?.caused_failure_edges ?? 0}
                  </span>
                  <span className="text-sm text-gray-500">caused_failure</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Search */}
          <Card>
            <CardContent className="p-4">
              <Input
                placeholder="Search clusters..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </CardContent>
          </Card>

          {/* Clusters table */}
          <Card>
            <CardHeader>
              <CardTitle>Problem Clusters</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {filteredClusters.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-gray-500 dark:text-gray-400">
                    {clusters.length === 0
                      ? 'No problem clusters yet. Run some sessions to generate clusters.'
                      : 'No clusters match your search.'}
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-1/2">Label</TableHead>
                      <TableHead className="text-center">Turns</TableHead>
                      <TableHead className="text-center">Success</TableHead>
                      <TableHead className="text-center">Rate</TableHead>
                      <TableHead className="text-center">Edges</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredClusters.map((cluster) => {
                      const successRate =
                        cluster.turn_count > 0
                          ? (cluster.success_count / cluster.turn_count) * 100
                          : 0;

                      const cleanLabel = cluster.label.split('\n')[0].slice(0, 100);

                      return (
                        <TableRow key={cluster.cluster_id}>
                          <TableCell>
                            <span className="block max-w-md truncate" title={cluster.label}>
                              {cleanLabel}
                              {cluster.label.length > 100 ? '...' : ''}
                            </span>
                          </TableCell>
                          <TableCell className="text-center">{cluster.turn_count}</TableCell>
                          <TableCell className="text-center">
                            <span className="text-green-600">{cluster.success_count}</span>
                            {' / '}
                            <span className="text-red-600">{cluster.failure_count}</span>
                          </TableCell>
                          <TableCell className="text-center">
                            <Badge
                              className={cn(
                                'text-xs',
                                successRate >= 70
                                  ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                                  : successRate >= 50
                                    ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                                    : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                              )}
                            >
                              {successRate.toFixed(0)}%
                            </Badge>
                          </TableCell>
                          <TableCell className="text-center">
                            <span className="text-green-600">{cluster.solved_by_edges}</span>
                            {' / '}
                            <span className="text-red-600">{cluster.caused_failure_edges}</span>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-md px-3 py-1 text-sm font-medium hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
              >
                Previous
              </button>
              <span className="text-sm text-gray-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-md px-3 py-1 text-sm font-medium hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default KnowledgeGraphPage;
