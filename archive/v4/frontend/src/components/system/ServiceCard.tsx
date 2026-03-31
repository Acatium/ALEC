/**
 * Service card component
 */

import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { HealthStatus } from './HealthStatus';
import { cn } from '@/lib/utils';
import type { ServiceConfig } from '@/api/types';

export interface ServiceCardProps {
  service: ServiceConfig;
  className?: string;
}

function ServiceCard({ service, className }: ServiceCardProps) {
  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-lg">{service.name}</CardTitle>
          <HealthStatus
            status={service.enabled ? 'healthy' : 'unknown'}
            label={service.enabled ? 'Enabled' : 'Disabled'}
          />
        </div>
        {service.description && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {service.description}
          </p>
        )}
      </CardHeader>

      <CardContent className="flex-1">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Version</span>
            <span>{service.version || '1.0.0'}</span>
          </div>
          {service.config && Object.keys(service.config).length > 0 && (
            <div className="mt-4 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
              <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">Configuration</h4>
              <div className="space-y-1">
                {Object.entries(service.config).slice(0, 4).map(([key, value]) => (
                  <div key={key} className="flex justify-between text-xs">
                    <span className="text-gray-500">{key}</span>
                    <span className="font-mono">{JSON.stringify(value)}</span>
                  </div>
                ))}
                {Object.keys(service.config).length > 4 && (
                  <p className="text-xs text-gray-500">
                    +{Object.keys(service.config).length - 4} more
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>

      <CardFooter>
        <Link to={`/system/services/${service.name}`} className="w-full">
          <Button variant="secondary" className="w-full">
            Configure
          </Button>
        </Link>
      </CardFooter>
    </Card>
  );
}

export { ServiceCard };
