/**
 * Send message mutation hook
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/api/chat';
import { sessionKeys } from '@/hooks/queries/useSessions';
import type { ChatRequest, ChatResponse } from '@/api/types';

export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ChatRequest) => chatApi.sendMessage(request),
    onSuccess: (data: ChatResponse) => {
      // Invalidate session queries to refresh lists
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() });

      // Update the specific session detail if it exists
      if (data.session_id) {
        queryClient.invalidateQueries({
          queryKey: sessionKeys.detail(data.session_id),
        });
        queryClient.invalidateQueries({
          queryKey: sessionKeys.history(data.session_id),
        });
      }
    },
  });
}

export function useCompleteSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      sessionId,
      status,
      reason,
    }: {
      sessionId: string;
      status: 'completed' | 'failed';
      reason?: string;
    }) => chatApi.completeSession(sessionId, { status, reason }),
    onSuccess: (_, { sessionId }) => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}
