/**
 * Experiments query hooks
 */

import { useQuery } from '@tanstack/react-query';
import { evaluationApi, type ExperimentListParams, type ExperimentResultsParams } from '@/api/evaluation';

export const experimentKeys = {
  all: ['experiments'] as const,
  lists: () => [...experimentKeys.all, 'list'] as const,
  list: (params: ExperimentListParams) => [...experimentKeys.lists(), params] as const,
  details: () => [...experimentKeys.all, 'detail'] as const,
  detail: (id: string) => [...experimentKeys.details(), id] as const,
  results: (id: string, params?: ExperimentResultsParams) =>
    [...experimentKeys.details(), id, 'results', params] as const,
  epochs: (ids: string[]) => [...experimentKeys.all, 'epochs', ids] as const,
};

export function useExperiments(params: ExperimentListParams = {}) {
  return useQuery({
    queryKey: experimentKeys.list(params),
    queryFn: () => evaluationApi.listExperiments(params),
    staleTime: 5_000, // 5s - experiments change frequently
    refetchInterval: 5_000, // Poll while running
  });
}

export function useExperiment(experimentId: string | undefined) {
  return useQuery({
    queryKey: experimentKeys.detail(experimentId || ''),
    queryFn: () => evaluationApi.getExperiment(experimentId!),
    enabled: !!experimentId,
    staleTime: 5_000,
    refetchInterval: (query) => {
      // Only poll if experiment is running
      const status = query.state.data?.status;
      return status === 'running' ? 5_000 : false;
    },
  });
}

export function useExperimentResults(
  experimentId: string | undefined,
  params: ExperimentResultsParams = {}
) {
  return useQuery({
    queryKey: experimentKeys.results(experimentId || '', params),
    queryFn: () => evaluationApi.getExperimentResults(experimentId!, params),
    enabled: !!experimentId,
    staleTime: 5_000,
  });
}

export function useEpochsComparison(experimentIds: string[] | undefined) {
  return useQuery({
    queryKey: experimentKeys.epochs(experimentIds ?? []),
    queryFn: () => evaluationApi.compareEpochs(experimentIds ?? []),
    enabled: (experimentIds?.length ?? 0) > 0,
    staleTime: 30_000,
  });
}
