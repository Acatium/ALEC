/**
 * Bullet mutation hooks
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { libraryApi } from '@/api/library';
import { bulletKeys } from '@/hooks/queries/useBullets';
import type { BulletUpdate, BulletResponse, BulletStatus } from '@/api/types';

export function useUpdateBullet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ bulletId, update }: { bulletId: string; update: BulletUpdate }) =>
      libraryApi.updateBullet(bulletId, update),
    onSuccess: (data: BulletResponse, { bulletId }) => {
      // Update the specific bullet in cache
      queryClient.setQueryData(bulletKeys.detail(bulletId), data);
      // Invalidate lists to refresh
      queryClient.invalidateQueries({ queryKey: bulletKeys.lists() });
    },
  });
}

export function useArchiveBullet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (bulletId: string) => libraryApi.archiveBullet(bulletId),
    onSuccess: (_, bulletId) => {
      queryClient.invalidateQueries({ queryKey: bulletKeys.detail(bulletId) });
      queryClient.invalidateQueries({ queryKey: bulletKeys.lists() });
    },
  });
}

export function useBulkUpdateStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ bulletIds, status }: { bulletIds: string[]; status: BulletStatus }) =>
      libraryApi.bulkUpdateStatus(bulletIds, status),
    onSuccess: () => {
      // Invalidate all bullet queries
      queryClient.invalidateQueries({ queryKey: bulletKeys.all });
    },
  });
}
