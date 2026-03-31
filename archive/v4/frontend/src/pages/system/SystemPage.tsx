/**
 * System Dashboard Page - v3
 *
 * Overview of system health, learning statistics, and administrative controls.
 */

import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useLearningStats, useIntelligence, useGraphHealth } from '@/hooks/queries/useSystem';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { HealthStatus } from '@/components/system/HealthStatus';
import { LearningStatsCard } from '@/components/system/LearningStatsCard';
import { ResetControls } from '@/components/system/ResetControls';
import { useRunIntelligence, useSynthesizeGaps } from '@/hooks/mutations/useSystemMutations';

function SystemPage() {
  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useLearningStats();
  const {
    data: intelligence,
    isLoading: intelligenceLoading,
    refetch: refetchIntelligence,
  } = useIntelligence();
  const { data: graphHealth, isLoading: graphLoading } = useGraphHealth();

  const runIntelligenceMutation = useRunIntelligence();
  const synthesizeGapsMutation = useSynthesizeGaps();

  const handleRunIntelligence = async () => {
    await runIntelligenceMutation.mutateAsync();
    refetchIntelligence();
  };

  const handleSynthesizeGaps = async () => {
    await synthesizeGapsMutation.mutateAsync(5);
    refetchIntelligence();
    refetchStats();
  };

  if (statsLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading system status..." />
      </AppLayout>
    );
  }

  if (statsError) {
    return (
      <AppLayout>
        <Error
          title="Failed to load system status"
          message={statsError.message}
          onRetry={() => refetchStats()}
          fullPage
        />
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-10 pb-12">
          {/* Header */}
          <div className="border-b border-gray-200 pb-6 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">System Dashboard</h1>
                <p className="mt-3 text-lg text-gray-600 dark:text-gray-300">
                  Monitor health, manage learning data, and view intelligence insights.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <HealthStatus status="healthy" label="System Healthy" />
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <Link to="/learning-loop">
                <Button variant="secondary" size="sm">
                  Learning Loop Docs
                </Button>
              </Link>
              <Link to="/evaluation">
                <Button variant="secondary" size="sm">
                  Evaluation
                </Button>
              </Link>
              <Link to="/library">
                <Button variant="secondary" size="sm">
                  Bullet Library
                </Button>
              </Link>
              <Link to="/knowledge-graph">
                <Button variant="secondary" size="sm">
                  Knowledge Graph
                </Button>
              </Link>
            </div>
          </div>

          {/* Quick Stats Grid */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Overview</h2>
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard
                label="Total Sessions"
                value={stats?.total_sessions ?? 0}
                subtext={`${stats?.successful_sessions ?? 0} successful`}
                color="blue"
              />
              <StatCard
                label="Total Bullets"
                value={stats?.total_bullets ?? 0}
                subtext={`${stats?.active_bullets ?? 0} active`}
                color="purple"
              />
              <StatCard
                label="Clusters"
                value={graphHealth?.total_clusters ?? 0}
                subtext={`${graphHealth?.active_clusters ?? 0} active`}
                color="green"
              />
              <StatCard
                label="Graph Edges"
                value={graphHealth?.total_edges ?? 0}
                subtext={`${graphHealth?.solved_by_edges ?? 0} solved_by`}
                color="amber"
              />
            </div>
          </section>

          {/* TODO: Event Processing section hidden - requires Prometheus aggregation across containers */}

          {/* Graph Health */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Knowledge Graph Health</h2>
            <div className="rounded-xl border border-gray-200 bg-gradient-to-b from-gray-50 to-white p-6 dark:border-gray-700 dark:from-gray-800 dark:to-gray-900">
              {graphLoading ? (
                <Loading text="Loading graph health..." />
              ) : graphHealth ? (
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                  <MetricCard
                    title="Clusters"
                    value={graphHealth.total_clusters}
                    subtitle={`${graphHealth.active_clusters} active`}
                    icon={
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                        />
                      </svg>
                    }
                  />
                  <MetricCard
                    title="solved_by Edges"
                    value={graphHealth.solved_by_edges}
                    subtitle="Proven solutions"
                    color="green"
                    icon={
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                    }
                  />
                  <MetricCard
                    title="caused_failure Edges"
                    value={graphHealth.caused_failure_edges}
                    subtitle="Cluster-specific exclusions"
                    color="red"
                    icon={
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        />
                      </svg>
                    }
                  />
                  <div className="md:col-span-2 lg:col-span-3">
                    <div className="flex items-center justify-between rounded-lg bg-gray-100 p-4 dark:bg-gray-800">
                      <div>
                        <span className="text-sm text-gray-500">Average Cluster Success Rate</span>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-2xl font-bold text-gray-900 dark:text-white">
                            {graphHealth.avg_cluster_success_rate.toFixed(1)}%
                          </span>
                          <SuccessRateBadge rate={graphHealth.avg_cluster_success_rate} />
                        </div>
                      </div>
                      <Link to="/knowledge-graph">
                        <Button variant="secondary" size="sm">
                          View Graph
                        </Button>
                      </Link>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-gray-500">No graph data available.</p>
              )}
            </div>
          </section>

          {/* Learning stats */}
          {stats && <LearningStatsCard stats={stats} />}

          {/* Intelligence Analysis */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Intelligence Analysis</h2>
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-3">
                    LIBRARIAN + STRATEGIST
                    <Badge variant="info">Analysis</Badge>
                  </CardTitle>
                  <div className="flex gap-2">
                    <Button
                      onClick={handleSynthesizeGaps}
                      loading={synthesizeGapsMutation.isPending}
                      size="sm"
                      variant="secondary"
                    >
                      Synthesize Gaps
                    </Button>
                    <Button
                      onClick={handleRunIntelligence}
                      loading={runIntelligenceMutation.isPending}
                      size="sm"
                    >
                      Run Analysis
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {intelligenceLoading ? (
                  <Loading text="Loading intelligence data..." />
                ) : intelligence ? (
                  <div className="space-y-6">
                    {/* Summary metrics */}
                    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                      <IntelligenceMetric
                        label="Knowledge Gaps"
                        value={intelligence.knowledge_gaps?.length ?? 0}
                        color="amber"
                        description="Clusters with failures but no solutions"
                      />
                      <IntelligenceMetric
                        label="Harmful Bullets"
                        value={intelligence.harmful_bullets?.length ?? 0}
                        color="red"
                        description="Bullets causing more harm than help"
                      />
                      <IntelligenceMetric
                        label="Struggling Clusters"
                        value={intelligence.struggling_clusters?.length ?? 0}
                        color="yellow"
                        description="Clusters with poor success rates"
                      />
                      <IntelligenceMetric
                        label="Recommendations"
                        value={intelligence.recommendations?.length ?? 0}
                        color="green"
                        description="Actionable insights"
                      />
                    </div>

                    {/* Knowledge Gaps */}
                    {intelligence.knowledge_gaps && intelligence.knowledge_gaps.length > 0 && (
                      <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
                        <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          Knowledge Gaps (No Solutions)
                        </h4>
                        <div className="space-y-2">
                          {intelligence.knowledge_gaps.slice(0, 5).map((gap) => (
                            <div
                              key={gap.cluster_id}
                              className="flex items-center justify-between rounded bg-white/60 px-3 py-2 text-sm dark:bg-gray-900/40"
                            >
                              <span className="text-gray-700 dark:text-gray-300">{gap.label}</span>
                              <div className="flex items-center gap-2">
                                <Badge variant="error" className="text-xs">
                                  {gap.failures} failures
                                </Badge>
                                <Badge variant="success" className="text-xs">
                                  {gap.successes} successes
                                </Badge>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Struggling Clusters */}
                    {intelligence.struggling_clusters && intelligence.struggling_clusters.length > 0 && (
                      <div className="mt-4 rounded-lg border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-900/20">
                        <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-yellow-700 dark:text-yellow-300">
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
                          </svg>
                          Struggling Clusters (Low Success Rate)
                        </h4>
                        <div className="space-y-2">
                          {intelligence.struggling_clusters.slice(0, 5).map((cluster) => (
                            <div
                              key={cluster.cluster_id}
                              className="flex items-center justify-between rounded bg-white/60 px-3 py-2 text-sm dark:bg-gray-900/40"
                            >
                              <span className="text-gray-700 dark:text-gray-300">{cluster.label}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-500">{cluster.turns} turns</span>
                                <SuccessRateBadge rate={cluster.success_rate} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Harmful Bullets */}
                    {intelligence.harmful_bullets && intelligence.harmful_bullets.length > 0 && (
                      <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                        <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-red-700 dark:text-red-300">
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                          </svg>
                          Harmful Bullets (More Harm Than Help)
                        </h4>
                        <div className="space-y-2">
                          {intelligence.harmful_bullets.slice(0, 5).map((bullet) => (
                            <Link
                              key={bullet.id}
                              to={`/library/${bullet.id}`}
                              className="flex items-center justify-between rounded bg-white/60 px-3 py-2 text-sm hover:bg-white dark:bg-gray-900/40 dark:hover:bg-gray-900/60"
                            >
                              <span className="truncate max-w-md text-gray-700 dark:text-gray-300">
                                {bullet.content}
                              </span>
                              <div className="flex items-center gap-2 ml-2">
                                <Badge variant="error" className="text-xs">
                                  -{bullet.harmful}
                                </Badge>
                                <Badge variant="success" className="text-xs">
                                  +{bullet.helpful}
                                </Badge>
                              </div>
                            </Link>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Empty state */}
                    {(!intelligence.knowledge_gaps || intelligence.knowledge_gaps.length === 0) &&
                      (!intelligence.struggling_clusters || intelligence.struggling_clusters.length === 0) &&
                      (!intelligence.harmful_bullets || intelligence.harmful_bullets.length === 0) && (
                        <div className="rounded-lg border border-green-200 bg-green-50 p-6 text-center dark:border-green-800 dark:bg-green-900/20">
                          <svg
                            className="mx-auto h-12 w-12 text-green-500"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          </svg>
                          <p className="mt-3 font-medium text-green-700 dark:text-green-300">
                            System is healthy
                          </p>
                          <p className="mt-1 text-sm text-green-600 dark:text-green-400">
                            No knowledge gaps, struggling clusters, or harmful bullets detected.
                          </p>
                        </div>
                      )}
                  </div>
                ) : (
                  <p className="text-gray-500 dark:text-gray-400">
                    Run intelligence analysis to get insights about the learning system.
                  </p>
                )}
              </CardContent>
            </Card>
          </section>

          {/* Reset controls */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Administrative Controls</h2>
            <ResetControls />
          </section>
        </div>
      </PageContainer>
    </AppLayout>
  );
}

// Helper Components

function StatCard({
  label,
  value,
  subtext,
  color = 'blue',
}: {
  label: string;
  value: number;
  subtext?: string;
  color?: 'blue' | 'purple' | 'green' | 'amber';
}) {
  const colorClasses = {
    blue: 'text-blue-600 dark:text-blue-400',
    purple: 'text-purple-600 dark:text-purple-400',
    green: 'text-green-600 dark:text-green-400',
    amber: 'text-amber-600 dark:text-amber-400',
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-center">
          <span className={`block text-3xl font-bold ${colorClasses[color]}`}>{value}</span>
          <span className="text-sm text-gray-500">{label}</span>
          {subtext && <span className="block mt-0.5 text-xs text-gray-400">{subtext}</span>}
        </div>
      </CardContent>
    </Card>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  icon,
  color = 'blue',
}: {
  title: string;
  value: number;
  subtitle?: string;
  icon?: React.ReactNode;
  color?: 'blue' | 'green' | 'red' | 'amber';
}) {
  const colorClasses = {
    blue: 'text-blue-500',
    green: 'text-green-500',
    red: 'text-red-500',
    amber: 'text-amber-500',
  };

  return (
    <div className="flex items-center gap-4 rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      {icon && <div className={colorClasses[color]}>{icon}</div>}
      <div>
        <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
        {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
      </div>
    </div>
  );
}

function IntelligenceMetric({
  label,
  value,
  color,
  description,
}: {
  label: string;
  value: number;
  color: 'amber' | 'red' | 'yellow' | 'green';
  description?: string;
}) {
  const colorClasses = {
    amber: 'text-amber-600 dark:text-amber-400',
    red: 'text-red-600 dark:text-red-400',
    yellow: 'text-yellow-600 dark:text-yellow-400',
    green: 'text-green-600 dark:text-green-400',
  };

  return (
    <div className="rounded-lg bg-gray-50 p-4 text-center dark:bg-gray-800">
      <span className={`block text-2xl font-bold ${colorClasses[color]}`}>{value}</span>
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
      {description && (
        <span className="block mt-1 text-xs text-gray-500 dark:text-gray-400">{description}</span>
      )}
    </div>
  );
}

function SuccessRateBadge({ rate }: { rate: number }) {
  const variant = rate >= 70 ? 'success' : rate >= 40 ? 'warning' : 'error';
  return (
    <Badge variant={variant} className="text-xs">
      {rate.toFixed(1)}%
    </Badge>
  );
}

export default SystemPage;
