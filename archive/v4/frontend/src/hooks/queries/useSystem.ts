/**
 * System query hooks
 */

import { useQuery } from '@tanstack/react-query';
import { systemApi } from '@/api/system';

export const systemKeys = {
  all: ['system'] as const,
  health: () => [...systemKeys.all, 'health'] as const,
  learningStats: () => [...systemKeys.all, 'learning-stats'] as const,
  learningHealth: () => [...systemKeys.all, 'learning-health'] as const,
  graphHealth: () => [...systemKeys.all, 'graph-health'] as const,
  clusters: (params?: { page?: number; page_size?: number; status?: string }) =>
    [...systemKeys.all, 'clusters', params] as const,
  edges: (params?: { edge_type?: string; limit?: number }) =>
    [...systemKeys.all, 'edges', params] as const,
  intelligence: () => [...systemKeys.all, 'intelligence'] as const,
  services: () => [...systemKeys.all, 'services'] as const,
  service: (name: string) => [...systemKeys.services(), name] as const,
  prompts: () => [...systemKeys.all, 'prompts'] as const,
  prompt: (service: string, name: string) => [...systemKeys.prompts(), service, name] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: systemKeys.health(),
    queryFn: () => systemApi.getHealth(),
    staleTime: 10_000, // 10s
    refetchInterval: 30_000, // Poll every 30s
  });
}

export function useLearningStats() {
  return useQuery({
    queryKey: systemKeys.learningStats(),
    queryFn: () => systemApi.getLearningStats(),
    staleTime: 30_000,
  });
}

export function useLearningHealth() {
  return useQuery({
    queryKey: systemKeys.learningHealth(),
    queryFn: () => systemApi.getLearningHealth(),
    staleTime: 10_000, // 10s - refresh frequently for monitoring
    refetchInterval: 30_000, // Poll every 30s
  });
}

export function useGraphHealth() {
  return useQuery({
    queryKey: systemKeys.graphHealth(),
    queryFn: () => systemApi.getGraphHealth(),
    staleTime: 30_000,
  });
}

export function useClusters(params?: { page?: number; page_size?: number; status?: string }) {
  return useQuery({
    queryKey: systemKeys.clusters(params),
    queryFn: () => systemApi.getClusters(params),
    staleTime: 30_000,
  });
}

export function useEdges(params?: { edge_type?: string; limit?: number }) {
  return useQuery({
    queryKey: systemKeys.edges(params),
    queryFn: () => systemApi.getEdges(params),
    staleTime: 30_000,
  });
}

export function useIntelligence() {
  return useQuery({
    queryKey: systemKeys.intelligence(),
    queryFn: () => systemApi.getIntelligence(),
    staleTime: 60_000, // 1min
  });
}

export function useServices() {
  return useQuery({
    queryKey: systemKeys.services(),
    queryFn: async () => {
      const response = await systemApi.listServices();
      return response.services;
    },
    staleTime: 60_000,
  });
}

export function useService(serviceName: string | undefined) {
  return useQuery({
    queryKey: systemKeys.service(serviceName || ''),
    queryFn: () => systemApi.getService(serviceName!),
    enabled: !!serviceName,
    staleTime: 60_000,
  });
}

export function usePrompts() {
  return useQuery({
    queryKey: systemKeys.prompts(),
    queryFn: async () => {
      const response = await systemApi.listPrompts();
      return response.prompts;
    },
    staleTime: 60_000,
  });
}

export function usePrompt(serviceName: string | undefined, promptName: string | undefined) {
  return useQuery({
    queryKey: systemKeys.prompt(serviceName || '', promptName || ''),
    queryFn: () => systemApi.getPrompt(serviceName!, promptName!),
    enabled: !!serviceName && !!promptName,
    staleTime: 60_000,
  });
}
