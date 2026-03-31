/**
 * System mutation hooks
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { systemApi } from '@/api/system';
import { systemKeys } from '@/hooks/queries/useSystem';
import { sessionKeys } from '@/hooks/queries/useSessions';
import { bulletKeys } from '@/hooks/queries/useBullets';
import { experimentKeys } from '@/hooks/queries/useExperiments';

export function useResetAll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetAll(),
    onSuccess: () => {
      // Invalidate everything
      queryClient.invalidateQueries();
    },
  });
}

export function useResetCounters() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetCounters(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bulletKeys.all });
      queryClient.invalidateQueries({ queryKey: systemKeys.learningStats() });
    },
  });
}

export function useResetSessions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetSessions(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.all });
      queryClient.invalidateQueries({ queryKey: systemKeys.learningStats() });
    },
  });
}

export function useResetEvaluations() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetEvaluations(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.all });
    },
  });
}

export function useResetRedis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetRedis(),
    onSuccess: () => {
      // Redis flush may affect cached bullets
      queryClient.invalidateQueries({ queryKey: sessionKeys.all });
    },
  });
}

export function useResetBullets() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.resetBullets(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bulletKeys.all });
      queryClient.invalidateQueries({ queryKey: systemKeys.all });
    },
  });
}

export function useRunIntelligence() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => systemApi.runIntelligence(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bulletKeys.all });
      queryClient.invalidateQueries({ queryKey: systemKeys.intelligence() });
      queryClient.invalidateQueries({ queryKey: systemKeys.learningStats() });
    },
  });
}

export function useSynthesizeGaps() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (maxGaps?: number) => systemApi.synthesizeGaps(maxGaps),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bulletKeys.all });
      queryClient.invalidateQueries({ queryKey: systemKeys.intelligence() });
    },
  });
}

export function useUpdateService() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      serviceName,
      config,
    }: {
      serviceName: string;
      config: Record<string, unknown>;
    }) => systemApi.updateService(serviceName, config),
    onSuccess: (_, { serviceName }) => {
      queryClient.invalidateQueries({ queryKey: systemKeys.service(serviceName) });
      queryClient.invalidateQueries({ queryKey: systemKeys.services() });
    },
  });
}

export function useUpdatePrompt() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      serviceName,
      promptName,
      content,
    }: {
      serviceName: string;
      promptName: string;
      content: string;
    }) => systemApi.updatePrompt(serviceName, promptName, content),
    onSuccess: (_, { serviceName, promptName }) => {
      queryClient.invalidateQueries({
        queryKey: systemKeys.prompt(serviceName, promptName),
      });
      queryClient.invalidateQueries({ queryKey: systemKeys.prompts() });
    },
  });
}
