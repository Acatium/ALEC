/**
 * Experiment mutation hooks
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { evaluationApi } from '@/api/evaluation';
import { experimentKeys } from '@/hooks/queries/useExperiments';
import type { ExperimentCreate } from '@/api/types';

export function useCreateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experiment: ExperimentCreate) => evaluationApi.createExperiment(experiment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.lists() });
    },
    onError: (error) => {
      console.error('useCreateExperiment failed:', error);
    },
  });
}

export function useStartExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experimentId: string) => evaluationApi.startExperiment(experimentId),
    onSuccess: (_, experimentId) => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.detail(experimentId) });
      queryClient.invalidateQueries({ queryKey: experimentKeys.lists() });
    },
  });
}

export function useStopExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experimentId: string) => evaluationApi.stopExperiment(experimentId),
    onSuccess: (_, experimentId) => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.detail(experimentId) });
      queryClient.invalidateQueries({ queryKey: experimentKeys.lists() });
    },
  });
}

export function useUpdateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      evaluationApi.updateExperiment(id, { name }),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: experimentKeys.lists() });
    },
  });
}

export function useDeleteExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experimentId: string) => evaluationApi.deleteExperiment(experimentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.all });
    },
  });
}
