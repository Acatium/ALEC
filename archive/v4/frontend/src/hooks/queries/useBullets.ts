/**
 * Bullets query hooks
 */

import { useQuery } from '@tanstack/react-query';
import { libraryApi } from '@/api/library';
import type { BulletListParams } from '@/api/types';

export const bulletKeys = {
  all: ['bullets'] as const,
  lists: () => [...bulletKeys.all, 'list'] as const,
  list: (params: BulletListParams) => [...bulletKeys.lists(), params] as const,
  details: () => [...bulletKeys.all, 'detail'] as const,
  detail: (id: string) => [...bulletKeys.details(), id] as const,
};

export function useBullets(params: BulletListParams = {}) {
  return useQuery({
    queryKey: bulletKeys.list(params),
    queryFn: () => libraryApi.listBullets(params),
    staleTime: 30_000, // 30s
  });
}

export function useBullet(bulletId: string | undefined) {
  return useQuery({
    queryKey: bulletKeys.detail(bulletId || ''),
    queryFn: () => libraryApi.getBullet(bulletId!),
    enabled: !!bulletId,
    staleTime: 30_000,
  });
}
