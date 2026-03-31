/**
 * Library API - /api/v1/library endpoints
 *
 * See: core/session/api/library_routes.py
 */

import { api, buildQueryString } from './client';
import type {
  BulletResponse,
  BulletUpdate,
  BulletListParams,
  BulletListResponse,
} from './types';

// ============================================================================
// API Functions
// ============================================================================

/**
 * List bullets with pagination and filters
 */
export async function listBullets(params: BulletListParams = {}): Promise<BulletListResponse> {
  const query = buildQueryString(params as Record<string, unknown>);
  return api.get<BulletListResponse>(`/library${query}`);
}

/**
 * Get a single bullet by ID
 */
export async function getBullet(bulletId: string): Promise<BulletResponse> {
  return api.get<BulletResponse>(`/library/${bulletId}`);
}

/**
 * Update a bullet (content, status, or category)
 */
export async function updateBullet(
  bulletId: string,
  update: BulletUpdate
): Promise<BulletResponse> {
  return api.patch<BulletResponse>(`/library/${bulletId}`, update);
}

/**
 * Archive a bullet (soft delete)
 */
export async function archiveBullet(bulletId: string): Promise<{ status: string; bullet_id: string }> {
  return api.delete<{ status: string; bullet_id: string }>(`/library/${bulletId}`);
}

/**
 * Bulk update bullet status
 */
export async function bulkUpdateStatus(
  bulletIds: string[],
  status: string
): Promise<{ updated: number }> {
  return api.post<{ updated: number }>('/library/bulk-status', {
    bullet_ids: bulletIds,
    status,
  });
}

// ============================================================================
// Export as namespace
// ============================================================================

export const libraryApi = {
  listBullets,
  getBullet,
  updateBullet,
  archiveBullet,
  bulkUpdateStatus,
};
