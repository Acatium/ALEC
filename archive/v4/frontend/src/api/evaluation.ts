/**
 * Evaluation API - /api/v1/evaluation endpoints
 *
 * See: core/session/api/evaluation_routes.py
 */

import { api, buildQueryString } from './client';
import type {
  ExperimentCreate,
  ExperimentResponse,
  ExperimentListResponse,
  ExperimentSummary,
  ExperimentResultsResponse,
  EpochsComparisonResponse,
} from './types';

// ============================================================================
// Request Types
// ============================================================================

export interface ExperimentListParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export interface ExperimentResultsParams {
  limit?: number;
  offset?: number;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * List evaluation experiments
 * Note: Backend returns raw array, we transform to ExperimentListResponse for frontend consistency
 */
export async function listExperiments(
  params: ExperimentListParams = {}
): Promise<ExperimentListResponse> {
  const query = buildQueryString(params as Record<string, unknown>);
  const response = await api.get<ExperimentSummary[]>(`/evaluation/experiments${query}`);
  // Backend returns raw array, wrap in expected format
  return {
    experiments: response,
    total: response.length,
  };
}

/**
 * Create a new experiment
 */
export async function createExperiment(
  experiment: ExperimentCreate
): Promise<ExperimentResponse> {
  return api.post<ExperimentResponse>('/evaluation/experiments', experiment);
}

/**
 * Get a single experiment by ID
 */
export async function getExperiment(experimentId: string): Promise<ExperimentResponse> {
  return api.get<ExperimentResponse>(`/evaluation/experiments/${experimentId}`);
}

/**
 * Update an experiment (e.g., rename)
 */
export async function updateExperiment(
  experimentId: string,
  update: { name?: string }
): Promise<{ id: string; name: string }> {
  return api.patch<{ id: string; name: string }>(`/evaluation/experiments/${experimentId}`, update);
}

/**
 * Delete an experiment and its results
 */
export async function deleteExperiment(
  experimentId: string
): Promise<{ status: string; id: string }> {
  return api.delete<{ status: string; id: string }>(`/evaluation/experiments/${experimentId}`);
}

/**
 * Start an experiment
 */
export async function startExperiment(
  experimentId: string
): Promise<{ status: string; id: string }> {
  return api.post<{ status: string; id: string }>(
    `/evaluation/experiments/${experimentId}/start`
  );
}

/**
 * Stop a running experiment
 */
export async function stopExperiment(
  experimentId: string
): Promise<{ status: string; id: string }> {
  return api.post<{ status: string; id: string }>(
    `/evaluation/experiments/${experimentId}/stop`
  );
}

/**
 * Get experiment task results
 */
export async function getExperimentResults(
  experimentId: string,
  params: ExperimentResultsParams = {}
): Promise<ExperimentResultsResponse> {
  const query = buildQueryString(params as Record<string, unknown>);
  return api.get<ExperimentResultsResponse>(
    `/evaluation/experiments/${experimentId}/results${query}`
  );
}

/**
 * Compare experiments (epochs)
 */
export async function compareEpochs(
  experimentIds: string[]
): Promise<EpochsComparisonResponse> {
  const query = `?experiment_ids=${experimentIds.join(',')}`;
  return api.get<EpochsComparisonResponse>(`/evaluation/epochs${query}`);
}

// ============================================================================
// Export as namespace
// ============================================================================

export const evaluationApi = {
  listExperiments,
  createExperiment,
  getExperiment,
  updateExperiment,
  deleteExperiment,
  startExperiment,
  stopExperiment,
  getExperimentResults,
  compareEpochs,
};
