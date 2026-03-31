/**
 * Sessions query hooks
 */

import { useQuery } from '@tanstack/react-query';
import { chatApi, type SessionListParams } from '@/api/chat';

export const sessionKeys = {
  all: ['sessions'] as const,
  lists: () => [...sessionKeys.all, 'list'] as const,
  list: (params: SessionListParams) => [...sessionKeys.lists(), params] as const,
  details: () => [...sessionKeys.all, 'detail'] as const,
  detail: (id: string) => [...sessionKeys.details(), id] as const,
  history: (id: string) => [...sessionKeys.details(), id, 'history'] as const,
  turns: (id: string) => [...sessionKeys.details(), id, 'turns'] as const,
  bullets: (id: string) => [...sessionKeys.details(), id, 'bullets'] as const,
};

export function useSessions(params: SessionListParams = {}) {
  return useQuery({
    queryKey: sessionKeys.list(params),
    queryFn: () => chatApi.listSessions(params),
    staleTime: 30_000, // 30s
  });
}

export function useSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.detail(sessionId || ''),
    queryFn: () => chatApi.getSession(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export function useSessionHistory(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.history(sessionId || ''),
    queryFn: () => chatApi.getSessionHistory(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export function useSessionTurns(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.turns(sessionId || ''),
    queryFn: () => chatApi.getSessionTurns(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export function useSessionBullets(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.bullets(sessionId || ''),
    queryFn: () => chatApi.getSessionBullets(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}
