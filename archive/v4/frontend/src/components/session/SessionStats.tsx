/**
 * Session stats component
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import type { Turn } from '@/api/types';

export interface SessionStatsProps {
  turns: Turn[];
  className?: string;
}

function SessionStats({ turns, className }: SessionStatsProps) {
  // Calculate stats
  const totalTurns = turns.length;
  const outcomes = {
    solved: turns.filter((t) => t.micro_outcome === 'solved').length,
    progress: turns.filter((t) => t.micro_outcome === 'progress').length,
    stuck: turns.filter((t) => t.micro_outcome === 'stuck').length,
    error: turns.filter((t) => t.micro_outcome === 'error').length,
  };

  const totalBulletsShown = turns.reduce((sum, t) => sum + t.bullets_shown.length, 0);
  const totalBulletsHelped = turns.reduce((sum, t) => sum + t.bullets_helped.length, 0);
  const totalBulletsHarmed = turns.reduce((sum, t) => sum + t.bullets_harmed.length, 0);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Session Statistics</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Turns */}
        <div className="space-y-1">
          <p className="text-2xl font-bold">{totalTurns}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">Total Turns</p>
        </div>

        {/* Outcomes */}
        <div className="space-y-1">
          <div className="flex gap-2 text-sm">
            <span className="text-green-600 dark:text-green-400">{outcomes.solved} solved</span>
            <span className="text-blue-600 dark:text-blue-400">{outcomes.progress} progress</span>
          </div>
          <div className="flex gap-2 text-sm">
            <span className="text-yellow-600 dark:text-yellow-400">{outcomes.stuck} stuck</span>
            <span className="text-red-600 dark:text-red-400">{outcomes.error} error</span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">Micro-outcomes</p>
        </div>

        {/* Bullets shown */}
        <div className="space-y-1">
          <p className="text-2xl font-bold">{totalBulletsShown}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">Bullets Shown</p>
        </div>

        {/* Bullet effectiveness */}
        <div className="space-y-1">
          <div className="flex gap-2">
            <span className="text-lg font-bold text-green-600 dark:text-green-400">
              +{totalBulletsHelped}
            </span>
            <span className="text-lg font-bold text-red-600 dark:text-red-400">
              -{totalBulletsHarmed}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">Helped / Harmed</p>
        </div>
      </CardContent>
    </Card>
  );
}

export { SessionStats };
