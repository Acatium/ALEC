/**
 * Learning curve chart component
 * Uses Recharts for visualization
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { cn } from '@/lib/utils';

export interface LearningCurveDataPoint {
  epoch: number;
  success_rate: number;
  tasks_completed: number;
  label?: string;
}

export interface LearningCurveChartProps {
  data: LearningCurveDataPoint[];
  height?: number;
  showLegend?: boolean;
  className?: string;
}

function LearningCurveChart({
  data,
  height = 300,
  showLegend = true,
  className,
}: LearningCurveChartProps) {
  if (data.length === 0) {
    return (
      <div
        className={cn(
          'flex items-center justify-center text-gray-500 dark:text-gray-400',
          className
        )}
        style={{ height }}
      >
        No data available
      </div>
    );
  }

  // Format data for chart
  const chartData = data.map((point) => ({
    ...point,
    success_rate_pct: (point.success_rate * 100).toFixed(1),
  }));

  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="epoch"
            label={{ value: 'Epoch', position: 'insideBottomRight', offset: -5 }}
            className="text-xs"
          />
          <YAxis
            domain={[0, 100]}
            label={{ value: 'Task Success %', angle: -90, position: 'insideLeft' }}
            className="text-xs"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-bg-primary)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375rem',
            }}
            formatter={(value: number) => [`${value}%`, 'Task Success']}
            labelFormatter={(label) => `Epoch ${label}`}
          />
          {showLegend && <Legend />}
          <Line
            type="monotone"
            dataKey="success_rate_pct"
            name="Task Success %"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ fill: '#3b82f6', strokeWidth: 2 }}
            activeDot={{ r: 6, fill: '#3b82f6' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export { LearningCurveChart };
