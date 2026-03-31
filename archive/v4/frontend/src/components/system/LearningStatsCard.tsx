/**
 * Learning stats card component
 */

import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import type { LearningStatsResponse } from '@/api/types';

export interface LearningStatsCardProps {
  stats: LearningStatsResponse;
  className?: string;
}

function LearningStatsCard({ stats, className }: LearningStatsCardProps) {
  const effectivenessPercent = (stats.avg_effectiveness * 100).toFixed(1);
  const sessionSuccessRate = stats.total_sessions > 0
    ? ((stats.successful_sessions / stats.total_sessions) * 100).toFixed(1)
    : '0.0';

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Learning Statistics</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Main metrics */}
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          <div className="text-center">
            <span className="block text-3xl font-bold text-blue-600 dark:text-blue-400">
              {stats.total_sessions}
            </span>
            <span className="text-sm text-gray-500">Total Sessions</span>
            <span className="block text-xs text-gray-400 mt-0.5">
              {stats.successful_sessions} successful ({sessionSuccessRate}%)
            </span>
          </div>
          <div className="text-center">
            <span className="block text-3xl font-bold text-purple-600 dark:text-purple-400">
              {stats.total_bullets}
            </span>
            <span className="text-sm text-gray-500">Total Bullets</span>
          </div>
          <div className="text-center">
            <span className="block text-3xl font-bold text-green-600 dark:text-green-400">
              {stats.active_bullets}
            </span>
            <span className="text-sm text-gray-500">Active Bullets</span>
          </div>
          <div className="text-center">
            <span className="block text-3xl font-bold text-amber-600 dark:text-amber-400">
              {effectivenessPercent}%
            </span>
            <span className="text-sm text-gray-500">Avg Effectiveness</span>
          </div>
        </div>

        {/* Top Bullets */}
        {stats.top_bullets && stats.top_bullets.length > 0 && (
          <div className="mt-6 border-t border-gray-200 pt-6 dark:border-gray-700">
            <h4 className="mb-4 text-sm font-medium text-gray-500">Top Performing Bullets</h4>
            <div className="space-y-2">
              {stats.top_bullets.slice(0, 5).map((bullet) => (
                <Link
                  key={bullet.id}
                  to={`/library/${bullet.id}`}
                  className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 p-3 hover:bg-gray-100 dark:border-gray-800 dark:bg-gray-800/50 dark:hover:bg-gray-800"
                >
                  <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-md">
                    {bullet.content}
                  </span>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    <Badge variant="success" className="text-xs">
                      +{bullet.helpful}
                    </Badge>
                    {bullet.harmful > 0 && (
                      <Badge variant="error" className="text-xs">
                        -{bullet.harmful}
                      </Badge>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Recent Changes */}
        {stats.recent_changes && stats.recent_changes.length > 0 && (
          <div className="mt-6 border-t border-gray-200 pt-6 dark:border-gray-700">
            <h4 className="mb-4 text-sm font-medium text-gray-500">Recent Changes</h4>
            <div className="space-y-2">
              {stats.recent_changes.slice(0, 5).map((change) => (
                <Link
                  key={change.id}
                  to={`/library/${change.id}`}
                  className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 p-3 hover:bg-gray-100 dark:border-gray-800 dark:bg-gray-800/50 dark:hover:bg-gray-800"
                >
                  <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-md">
                    {change.content || 'No content'}
                  </span>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    <StatusBadge status={change.status} />
                    <span className="text-xs text-gray-400">
                      {formatRelativeTime(change.updated_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === 'active' ? 'success'
    : status === 'candidate' ? 'info'
    : status === 'archived' ? 'warning'
    : 'default';

  return (
    <Badge variant={variant} className="text-xs capitalize">
      {status}
    </Badge>
  );
}

function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return '';

  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

export { LearningStatsCard };
