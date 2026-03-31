/**
 * Session detail page
 */

import { useParams } from 'react-router-dom';
import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { useSession, useSessionHistory, useSessionTurns } from '@/hooks/queries/useSessions';
import { Loading } from '@/components/shared/Loading';
import { Error } from '@/components/shared/Error';
import { SessionHeader } from '@/components/session/SessionHeader';
import { SessionStats } from '@/components/session/SessionStats';
import { SessionTimeline } from '@/components/session/SessionTimeline';
import type { Turn, SessionMetadata } from '@/api/types';

function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();

  const {
    data: session,
    isLoading: sessionLoading,
    error: sessionError,
    refetch: refetchSession,
  } = useSession(sessionId);

  const {
    data: history,
    isLoading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useSessionHistory(sessionId);

  const {
    data: turnsData,
    isLoading: turnsLoading,
    error: turnsError,
    refetch: refetchTurns,
  } = useSessionTurns(sessionId);

  const isLoading = sessionLoading || historyLoading || turnsLoading;
  const error = sessionError || historyError || turnsError;

  if (isLoading) {
    return (
      <AppLayout>
        <Loading fullPage text="Loading session..." />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <Error
          title="Failed to load session"
          message={error.message}
          onRetry={() => {
            refetchSession();
            refetchHistory();
            refetchTurns();
          }}
          fullPage
        />
      </AppLayout>
    );
  }

  if (!session) {
    return (
      <AppLayout>
        <Error title="Session not found" message="The requested session does not exist" fullPage />
      </AppLayout>
    );
  }

  // Build session metadata from session response
  const sessionMetadata: SessionMetadata = {
    session_id: session.session_id,
    user_id: null,
    title: history?.title ?? null,
    domain: history?.domain ?? 'general',
    playbook_id: null,
    status: session.status,
    metadata: history?.metadata ?? {},
    message_count: session.message_count,
    token_usage: session.token_usage,
    duration_ms: null,
    micro_outcomes: turnsData?.micro_outcomes ?? null,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };

  // Use turns from the turns endpoint (includes micro_outcomes and attribution)
  const turns: Turn[] = turnsData?.turns.map((t) => ({
    turn_id: t.turn_id,
    turn_number: t.turn_number,
    user_message: t.user_message ?? '',
    assistant_response: t.assistant_response ?? '',
    sub_task: t.sub_task,
    micro_outcome: t.micro_outcome,
    error_trace: null,
    bullets_shown: t.bullets_shown,
    bullets_helped: t.bullets_helped,
    bullets_harmed: t.bullets_harmed,
    bullets_irrelevant: [],
    created_at: t.created_at,
  })) ?? [];

  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-6">
          <SessionHeader session={sessionMetadata} />
          <SessionStats turns={turns} />
          <div>
            <h2 className="mb-4 text-lg font-semibold">Conversation Timeline</h2>
            <SessionTimeline turns={turns} />
          </div>
        </div>
      </PageContainer>
    </AppLayout>
  );
}

export default SessionDetailPage;
