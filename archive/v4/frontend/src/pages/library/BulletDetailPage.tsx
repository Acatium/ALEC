/**
 * AKU detail page (v4)
 */

import { useParams, Link } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useBullet } from '@/hooks/queries/useBullets';
import { useSessions } from '@/hooks/queries/useSessions';
import { useUpdateBullet, useArchiveBullet } from '@/hooks/mutations/useUpdateBullet';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ChevronLeftIcon } from '@/components/ui/Icons';
import {
  formatDate,
  statusToColor,
  calculateEffectiveness,
  formatPercent,
} from '@/lib/utils';
import { BULLET_STATUSES } from '@/lib/constants';
import { useState } from 'react';
import type { BulletStatus } from '@/api/types';

const STATUS_OPTIONS = BULLET_STATUSES.map((s) => ({
  value: s,
  label: s.charAt(0).toUpperCase() + s.slice(1),
}));

function BulletDetailPage() {
  const { bulletId } = useParams<{ bulletId: string }>();
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  const { data: bullet, isLoading, error, refetch } = useBullet(bulletId);
  const updateMutation = useUpdateBullet();
  const archiveMutation = useArchiveBullet();

  // Get sessions that used this bullet
  const { data: sessionsData } = useSessions({ bullet_id: bulletId, limit: 10 });

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading bullet..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load bullet"
          message={error.message}
          onRetry={() => refetch()}
          fullPage
        />
      </AppLayout>
    );
  }

  if (!bullet) {
    return (
      <AppLayout>
        <Error title="Bullet not found" message="The requested bullet does not exist" fullPage />
      </AppLayout>
    );
  }

  const effectiveness = calculateEffectiveness(
    bullet.helpful_count,
    bullet.harmful_count,
    bullet.neutral_count
  );

  const handleStatusChange = async (newStatus: BulletStatus) => {
    await updateMutation.mutateAsync({
      bulletId: bullet.id,
      update: { status: newStatus },
    });
  };

  const handleArchive = async () => {
    await archiveMutation.mutateAsync(bullet.id);
    setShowArchiveDialog(false);
  };

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          {/* Back link */}
          <Link to="/bullets">
            <Button variant="ghost" size="sm" className="gap-1">
              <ChevronLeftIcon className="h-4 w-4" />
              Back to Library
            </Button>
          </Link>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{bullet.situation}</h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{bullet.id}</p>
          </div>
          <Badge className={statusToColor(bullet.status)}>{bullet.status}</Badge>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Content card */}
            <Card>
              <CardHeader>
                <CardTitle>Content</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Situation (When)
                  </h4>
                  <p className="mt-1">{bullet.situation}</p>
                </div>
                <div>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Assertion (What)
                  </h4>
                  <p className="mt-1">{bullet.assertion}</p>
                </div>
              </CardContent>
            </Card>

            {/* Sessions using this bullet */}
            <Card>
              <CardHeader>
                <CardTitle>Sessions Using This Bullet</CardTitle>
              </CardHeader>
              <CardContent>
                {sessionsData?.sessions && sessionsData.sessions.length > 0 ? (
                  <ul className="space-y-2">
                    {sessionsData.sessions.map((session) => (
                      <li key={session.session_id}>
                        <Link
                          to={`/sessions/${session.session_id}`}
                          className="text-blue-600 hover:underline dark:text-blue-400"
                        >
                          {session.title || session.session_id.slice(0, 20)}...
                        </Link>
                        <span className="ml-2 text-sm text-gray-500">
                          ({formatDate(session.created_at)})
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500 dark:text-gray-400">
                    No sessions have used this bullet yet
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Effectiveness card */}
            <Card>
              <CardHeader>
                <CardTitle>Effectiveness</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center">
                  <span className="text-4xl font-bold">{formatPercent(effectiveness)}</span>
                  <p className="text-sm text-gray-500">Overall Score</p>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                      {bullet.helpful_count}
                    </span>
                    <p className="text-xs text-gray-500">Helped</p>
                  </div>
                  <div>
                    <span className="text-lg font-semibold text-red-600 dark:text-red-400">
                      {bullet.harmful_count}
                    </span>
                    <p className="text-xs text-gray-500">Harmed</p>
                  </div>
                  <div>
                    <span className="text-lg font-semibold text-gray-600 dark:text-gray-400">
                      {bullet.neutral_count}
                    </span>
                    <p className="text-xs text-gray-500">Neutral</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Actions card */}
            <Card>
              <CardHeader>
                <CardTitle>Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Change Status</label>
                  <Select
                    options={STATUS_OPTIONS}
                    value={bullet.status}
                    onChange={(e) => handleStatusChange(e.target.value as BulletStatus)}
                    className="mt-1"
                  />
                </div>
              </CardContent>
              <CardFooter>
                <Button
                  variant="destructive"
                  onClick={() => setShowArchiveDialog(true)}
                  disabled={bullet.status === 'archived'}
                  className="w-full"
                >
                  Archive Bullet
                </Button>
              </CardFooter>
            </Card>

            {/* Metadata card */}
            <Card>
              <CardHeader>
                <CardTitle>Metadata</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Created</span>
                  <span>{formatDate(bullet.created_at)}</span>
                </div>
              </CardContent>
            </Card>
            </div>
          </div>
        </div>
      </PageContainer>

      {/* Archive confirmation dialog */}
      <ConfirmDialog
        open={showArchiveDialog}
        onClose={() => setShowArchiveDialog(false)}
        onConfirm={handleArchive}
        title="Archive Bullet?"
        description="This will archive the bullet. It will no longer be shown to users but can be reactivated later."
        confirmText="Archive"
        variant="destructive"
        loading={archiveMutation.isPending}
      />
    </AppLayout>
  );
}

export default BulletDetailPage;
