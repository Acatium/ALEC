/**
 * Evaluation Trends Chart
 * Collapsible chart showing learning metrics over time
 */

import { useState, useMemo } from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { ChevronDownIcon, ChevronUpIcon, TrendingUpIcon } from '@/components/ui/Icons';
import { cn } from '@/lib/utils';
import type { ExperimentSummary } from '@/api/types';

// Time window options
const TIME_WINDOWS = [
  { value: 'all', label: 'All time' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
];

// Metric toggle configuration
const METRICS = [
  { key: 'success_rate', label: 'Task Success %', color: '#22c55e', yAxisId: 'left' },
  { key: 'assertion_rate', label: 'Assertion Pass %', color: '#3b82f6', yAxisId: 'left' },
  { key: 'avg_tokens', label: 'Avg Tokens (K)', color: '#f59e0b', yAxisId: 'right' },
] as const;

type MetricKey = typeof METRICS[number]['key'];

interface EvaluationTrendsChartProps {
  experiments: ExperimentSummary[];
  className?: string;
}

interface ChartDataPoint {
  date: string;
  name: string;
  success_rate: number | null;
  assertion_rate: number | null;
  avg_tokens: number | null;
  tasks_completed: number;
  rawDate: Date;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartDataPoint }>;
  label?: string;
}

function EvaluationTrendsChart({ experiments, className }: EvaluationTrendsChartProps) {
  // Collapse state with localStorage persistence
  const [isExpanded, setIsExpanded] = useState(() => {
    const saved = localStorage.getItem('evaluation-trends-expanded');
    return saved !== null ? saved === 'true' : true; // Default expanded
  });

  const [timeWindow, setTimeWindow] = useState('all');
  const [enabledMetrics, setEnabledMetrics] = useState<Set<MetricKey>>(
    new Set(['success_rate', 'assertion_rate', 'avg_tokens'])
  );

  // Toggle collapse and persist
  const toggleExpanded = () => {
    const newValue = !isExpanded;
    setIsExpanded(newValue);
    localStorage.setItem('evaluation-trends-expanded', String(newValue));
  };

  // Toggle metric visibility
  const toggleMetric = (key: MetricKey) => {
    setEnabledMetrics((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        // Don't allow disabling all metrics
        if (next.size > 1) {
          next.delete(key);
        }
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Filter experiments by time window and prepare chart data
  const chartData = useMemo(() => {
    // Filter by completed status only (we want meaningful results)
    let filtered = experiments.filter((e) => e.status === 'completed');

    // Apply time window filter
    if (timeWindow !== 'all') {
      const days = parseInt(timeWindow);
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - days);
      filtered = filtered.filter((e) => new Date(e.created_at) >= cutoff);
    }

    // Sort by created_at ascending for timeline
    const sorted = [...filtered].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );

    // Transform to chart data
    return sorted.map((e): ChartDataPoint => {
      const assertionRate = e.total_assertions > 0
        ? (e.passed_assertions / e.total_assertions) * 100
        : null;

      return {
        date: new Date(e.created_at).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        }),
        name: e.name,
        success_rate: e.success_rate !== null ? e.success_rate * 100 : null,
        assertion_rate: assertionRate,
        avg_tokens: e.avg_tokens !== null ? e.avg_tokens / 1000 : null, // Convert to K
        tasks_completed: e.tasks_completed,
        rawDate: new Date(e.created_at),
      };
    });
  }, [experiments, timeWindow]);

  // Calculate summary stats
  const stats = useMemo(() => {
    if (chartData.length === 0) return null;

    const validSuccessRates = chartData
      .map((d) => d.success_rate)
      .filter((v): v is number => v !== null);
    const validTokens = chartData
      .map((d) => d.avg_tokens)
      .filter((v): v is number => v !== null);

    const avgSuccessRate = validSuccessRates.length > 0
      ? validSuccessRates.reduce((a, b) => a + b, 0) / validSuccessRates.length
      : null;

    const totalTokens = validTokens.length > 0
      ? validTokens.reduce((a, b) => a + b, 0)
      : null;

    // Calculate trend (last 3 vs first 3)
    let trend: 'up' | 'down' | 'flat' = 'flat';
    if (validSuccessRates.length >= 6) {
      const firstThreeAvg = validSuccessRates.slice(0, 3).reduce((a, b) => a + b, 0) / 3;
      const lastThreeAvg = validSuccessRates.slice(-3).reduce((a, b) => a + b, 0) / 3;
      if (lastThreeAvg > firstThreeAvg + 5) trend = 'up';
      else if (lastThreeAvg < firstThreeAvg - 5) trend = 'down';
    }

    return {
      totalExperiments: chartData.length,
      avgSuccessRate,
      totalTokensK: totalTokens,
      trend,
    };
  }, [chartData]);

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
    if (!active || !payload || payload.length === 0) return null;

    const data = payload[0]?.payload;

    return (
      <div className="rounded-lg border bg-white p-3 shadow-lg dark:bg-gray-800 dark:border-gray-700">
        <p className="font-medium text-sm mb-2">{data.name}</p>
        <p className="text-xs text-gray-500 mb-2">{label}</p>
        <div className="space-y-1 text-sm">
          {data.success_rate !== null && enabledMetrics.has('success_rate') && (
            <p className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-green-500" />
              Task Success: {data.success_rate.toFixed(1)}%
            </p>
          )}
          {data.assertion_rate !== null && enabledMetrics.has('assertion_rate') && (
            <p className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-blue-500" />
              Assertions: {data.assertion_rate.toFixed(1)}%
            </p>
          )}
          {data.avg_tokens !== null && enabledMetrics.has('avg_tokens') && (
            <p className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-amber-500" />
              Tokens: {data.avg_tokens.toFixed(1)}K
            </p>
          )}
          <p className="text-gray-500 text-xs mt-1">
            Tasks: {data.tasks_completed}
          </p>
        </div>
      </div>
    );
  };

  // Don't render if no experiments
  if (experiments.length === 0) return null;

  return (
    <Card className={cn('overflow-hidden', className)}>
      {/* Header - always visible */}
      <CardHeader
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        onClick={toggleExpanded}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TrendingUpIcon className="h-5 w-5 text-blue-500" />
            <CardTitle className="text-base font-semibold">Learning Trends</CardTitle>
            {stats && (
              <div className="flex items-center gap-4 text-sm text-gray-500">
                <span>{stats.totalExperiments} experiments</span>
                {stats.avgSuccessRate !== null && (
                  <span className="flex items-center gap-1">
                    <span className={cn(
                      'font-medium',
                      stats.avgSuccessRate >= 70 ? 'text-green-600' :
                      stats.avgSuccessRate >= 50 ? 'text-amber-600' : 'text-red-600'
                    )}>
                      {stats.avgSuccessRate.toFixed(1)}%
                    </span>
                    avg task success
                    {stats.trend !== 'flat' && (
                      <span className={cn(
                        'text-xs',
                        stats.trend === 'up' ? 'text-green-500' : 'text-red-500'
                      )}>
                        {stats.trend === 'up' ? '(improving)' : '(declining)'}
                      </span>
                    )}
                  </span>
                )}
              </div>
            )}
          </div>
          <Button variant="ghost" size="sm" className="p-1" onClick={(e) => { e.stopPropagation(); toggleExpanded(); }}>
            {isExpanded ? (
              <ChevronUpIcon className="h-5 w-5" />
            ) : (
              <ChevronDownIcon className="h-5 w-5" />
            )}
          </Button>
        </div>
      </CardHeader>

      {/* Collapsible content */}
      {isExpanded && (
        <CardContent className="border-t border-gray-200 dark:border-gray-700 pt-4">
          {/* Controls */}
          <div className="flex items-center justify-between mb-4">
            {/* Time window selector */}
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-500">Time:</label>
              <Select
                value={timeWindow}
                onChange={(e) => setTimeWindow(e.target.value)}
                options={TIME_WINDOWS}
                className="w-36"
              />
            </div>

            {/* Metric toggles */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">Show:</span>
              {METRICS.map((metric) => (
                <button
                  key={metric.key}
                  onClick={() => toggleMetric(metric.key)}
                  className={cn(
                    'px-2 py-1 text-xs rounded-full border transition-colors',
                    enabledMetrics.has(metric.key)
                      ? 'border-transparent text-white'
                      : 'border-gray-300 bg-transparent text-gray-500 hover:border-gray-400'
                  )}
                  style={{
                    backgroundColor: enabledMetrics.has(metric.key) ? metric.color : undefined,
                  }}
                >
                  {metric.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chart */}
          {chartData.length === 0 ? (
            <div className="flex items-center justify-center h-64 text-gray-500">
              No completed experiments in selected time window
            </div>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    className="text-xs"
                  />
                  {/* Left Y-axis for percentages */}
                  <YAxis
                    yAxisId="left"
                    domain={[0, 100]}
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `${v}%`}
                    className="text-xs"
                  />
                  {/* Right Y-axis for tokens */}
                  {enabledMetrics.has('avg_tokens') && (
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `${v}K`}
                      className="text-xs"
                    />
                  )}
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    wrapperStyle={{ fontSize: 12 }}
                    formatter={(value) => <span className="text-gray-600 dark:text-gray-400">{value}</span>}
                  />

                  {/* Task Success Line */}
                  {enabledMetrics.has('success_rate') && (
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="success_rate"
                      name="Task Success %"
                      stroke="#22c55e"
                      strokeWidth={2}
                      dot={{ fill: '#22c55e', strokeWidth: 0, r: 4 }}
                      activeDot={{ r: 6 }}
                      connectNulls
                    />
                  )}

                  {/* Assertion Pass Line */}
                  {enabledMetrics.has('assertion_rate') && (
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="assertion_rate"
                      name="Assertion Pass %"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={{ fill: '#3b82f6', strokeWidth: 0, r: 4 }}
                      activeDot={{ r: 6 }}
                      connectNulls
                    />
                  )}

                  {/* Tokens Area/Line */}
                  {enabledMetrics.has('avg_tokens') && (
                    <Area
                      yAxisId="right"
                      type="monotone"
                      dataKey="avg_tokens"
                      name="Avg Tokens (K)"
                      stroke="#f59e0b"
                      fill="#f59e0b"
                      fillOpacity={0.1}
                      strokeWidth={2}
                      connectNulls
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Summary stats footer */}
          {stats && chartData.length > 0 && (
            <div className="flex items-center justify-around mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-sm">
              <div className="text-center">
                <p className="text-gray-500">Experiments</p>
                <p className="font-semibold text-lg">{stats.totalExperiments}</p>
              </div>
              <div className="text-center">
                <p className="text-gray-500">Avg Task Success</p>
                <p className={cn(
                  'font-semibold text-lg',
                  stats.avgSuccessRate !== null && stats.avgSuccessRate >= 70 ? 'text-green-600' :
                  stats.avgSuccessRate !== null && stats.avgSuccessRate >= 50 ? 'text-amber-600' : 'text-red-600'
                )}>
                  {stats.avgSuccessRate !== null ? `${stats.avgSuccessRate.toFixed(1)}%` : '-'}
                </p>
              </div>
              <div className="text-center">
                <p className="text-gray-500">Total Tokens</p>
                <p className="font-semibold text-lg">
                  {stats.totalTokensK !== null ? `${stats.totalTokensK.toFixed(0)}K` : '-'}
                </p>
              </div>
              <div className="text-center">
                <p className="text-gray-500">Trend</p>
                <p className={cn(
                  'font-semibold text-lg',
                  stats.trend === 'up' ? 'text-green-600' :
                  stats.trend === 'down' ? 'text-red-600' : 'text-gray-500'
                )}>
                  {stats.trend === 'up' ? 'Improving' :
                   stats.trend === 'down' ? 'Declining' : 'Stable'}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

export { EvaluationTrendsChart };
