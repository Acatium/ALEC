/**
 * System API - /api/v1/system endpoints
 *
 * See: core/session/api/system_routes.py
 */

import { api } from './client';
import type {
  HealthResponse,
  LearningStatsResponse,
  LearningHealthResponse,
  IntelligenceReport,
  GraphHealthResponse,
  ClusterListResponse,
  EdgeListResponse,
  ServiceConfig,
  ServicePrompt,
} from './types';

// ============================================================================
// Health & Status
// ============================================================================

/**
 * Get system health status
 */
export async function getHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>('/system/health');
}

/**
 * Get learning statistics
 */
export async function getLearningStats(): Promise<LearningStatsResponse> {
  return api.get<LearningStatsResponse>('/system/learning-stats');
}

/**
 * Get knowledge graph health
 */
export async function getGraphHealth(): Promise<GraphHealthResponse> {
  return api.get<GraphHealthResponse>('/system/graph-health');
}

/**
 * Get learning system health (event processing, drop rates)
 */
export async function getLearningHealth(): Promise<LearningHealthResponse> {
  return api.get<LearningHealthResponse>('/system/diagnostic/learning-health');
}

/**
 * Get problem clusters with pagination
 */
export async function getClusters(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<ClusterListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set('page', params.page.toString());
  if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
  if (params?.status) searchParams.set('status', params.status);

  const queryString = searchParams.toString();
  const url = queryString ? `/system/clusters?${queryString}` : '/system/clusters';
  return api.get<ClusterListResponse>(url);
}

/**
 * Get knowledge edges for graph visualization
 */
export async function getEdges(params?: {
  edge_type?: string;
  limit?: number;
}): Promise<EdgeListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.edge_type) searchParams.set('edge_type', params.edge_type);
  if (params?.limit) searchParams.set('limit', params.limit.toString());

  const queryString = searchParams.toString();
  const url = queryString ? `/system/edges?${queryString}` : '/system/edges';
  return api.get<EdgeListResponse>(url);
}

// ============================================================================
// Reset Operations
// ============================================================================

/**
 * Reset all data
 */
export async function resetAll(): Promise<{ status: string; timestamp: string }> {
  return api.post<{ status: string; timestamp: string }>('/system/reset?confirm=true');
}

/**
 * Reset bullet effectiveness counters
 */
export async function resetCounters(): Promise<{ status: string; target: string }> {
  return api.post<{ status: string; target: string }>('/system/reset/counters');
}

/**
 * Clear all sessions
 */
export async function resetSessions(): Promise<{ status: string; target: string }> {
  return api.post<{ status: string; target: string }>('/system/reset/sessions');
}

/**
 * Clear evaluation data
 */
export async function resetEvaluations(): Promise<{ status: string; target: string }> {
  return api.post<{ status: string; target: string }>('/system/reset/evaluations');
}

/**
 * Flush Redis cache
 */
export async function resetRedis(): Promise<{ status: string; target: string }> {
  return api.post<{ status: string; target: string }>('/system/reset/redis');
}

/**
 * Delete all bullets (DESTRUCTIVE)
 */
export async function resetBullets(): Promise<{ status: string; target: string }> {
  return api.post<{ status: string; target: string }>('/system/reset/bullets?confirm=true');
}

// ============================================================================
// Intelligence
// ============================================================================

/**
 * Get intelligence analysis report
 */
export async function getIntelligence(): Promise<IntelligenceReport> {
  return api.get<IntelligenceReport>('/system/intelligence');
}

/**
 * Run intelligence analysis (archives harmful bullets)
 */
export async function runIntelligence(): Promise<{
  status: string;
  bullets_archived: number;
  timestamp: string;
}> {
  return api.post<{ status: string; bullets_archived: number; timestamp: string }>(
    '/system/intelligence/run'
  );
}

/**
 * Trigger synthesis to fill knowledge gaps
 */
export async function synthesizeGaps(
  maxGaps?: number
): Promise<{ status: string; synthesized: number }> {
  const body = maxGaps !== undefined ? { max_gaps: maxGaps } : undefined;
  return api.post<{ status: string; synthesized: number }>(
    '/system/intelligence/synthesize',
    body
  );
}

// ============================================================================
// Services & Prompts (stub endpoints - may need backend implementation)
// ============================================================================

/**
 * List service configurations
 */
export async function listServices(): Promise<{ services: ServiceConfig[] }> {
  return api.get<{ services: ServiceConfig[] }>('/system/services');
}

/**
 * Get service configuration
 */
export async function getService(serviceName: string): Promise<ServiceConfig> {
  return api.get<ServiceConfig>(`/system/services/${serviceName}`);
}

/**
 * Update service configuration
 */
export async function updateService(
  serviceName: string,
  config: Record<string, unknown>
): Promise<ServiceConfig> {
  return api.patch<ServiceConfig>(`/system/services/${serviceName}`, { config });
}

/**
 * List prompts
 */
export async function listPrompts(): Promise<{ prompts: ServicePrompt[] }> {
  return api.get<{ prompts: ServicePrompt[] }>('/system/prompts');
}

/**
 * Get a prompt
 */
export async function getPrompt(
  serviceName: string,
  promptName: string
): Promise<ServicePrompt> {
  return api.get<ServicePrompt>(`/system/prompts/${serviceName}/${promptName}`);
}

/**
 * Update a prompt
 */
export async function updatePrompt(
  serviceName: string,
  promptName: string,
  content: string
): Promise<ServicePrompt> {
  return api.patch<ServicePrompt>(`/system/prompts/${serviceName}/${promptName}`, { content });
}

// ============================================================================
// Export as namespace
// ============================================================================

export const systemApi = {
  getHealth,
  getLearningStats,
  getLearningHealth,
  getGraphHealth,
  getClusters,
  getEdges,
  resetAll,
  resetCounters,
  resetSessions,
  resetEvaluations,
  resetRedis,
  resetBullets,
  getIntelligence,
  runIntelligence,
  synthesizeGaps,
  listServices,
  getService,
  updateService,
  listPrompts,
  getPrompt,
  updatePrompt,
};
