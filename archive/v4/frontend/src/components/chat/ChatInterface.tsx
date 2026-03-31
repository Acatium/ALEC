import { useEffect, useRef, useState } from 'react';
import { useChat } from '@/hooks/useChat';
import { Button } from '@/components/ui/Button';

interface ToolCall {
  name: string;
  input?: Record<string, unknown>;
}

interface ChatInterfaceProps {
  sessionId?: string;
}

export function ChatInterface({ sessionId }: ChatInterfaceProps) {
  const { session, sendMessage, createSession, loadHistory } = useChat(sessionId);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session.messages]);

  // Load session history or create new session on mount
  useEffect(() => {
    if (sessionId) {
      loadHistory(sessionId);
    } else {
      createSession();
    }
  }, [sessionId, loadHistory, createSession]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || session.isStreaming) return;

    await sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages Container - Centered with max-width */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-8 py-6 space-y-6">
          {session.messages.length === 0 && (
            <div className="flex items-center justify-center min-h-[70vh]">
              <div className="text-center space-y-6 max-w-2xl">
                <div>
                  <h1 className="text-5xl font-semibold mb-3">ALEC</h1>
                  <p className="text-xl text-muted-foreground">
                    How can I help you today?
                  </p>
                </div>
                <div className="space-y-3 text-base text-muted-foreground">
                  <p className="font-medium">Start by describing your task or question</p>
                </div>
              </div>
            </div>
          )}

          {session.messages.map((message) => (
            <div key={message.id} className="flex flex-col">
              <div className="flex items-start gap-4">
                {/* Message Label */}
                <div className={`flex-shrink-0 text-sm font-semibold text-muted-foreground min-w-[60px] ${
                  message.role === 'user' ? 'text-right' : ''
                }`}>
                  {message.role === 'user' ? 'You' : 'ALEC'}
                </div>

                {/* Message Content */}
                <div className="flex-1 min-w-0">
                  <div className={`rounded-lg px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-muted/50 border-l-2 border-primary'
                      : 'bg-muted/30 border-l-2 border-muted'
                  }`}>
                    <div className="whitespace-pre-wrap break-words text-base leading-relaxed">
                      {message.content}
                    </div>
                  </div>

                  {message.metadata?.tool_calls && message.metadata.tool_calls.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.metadata.tool_calls.map((tc: ToolCall, idx: number) => (
                        <div key={idx} className="inline-flex items-center gap-1.5 text-sm bg-muted border border-border rounded px-3 py-1">
                          <span className="opacity-70">🔧</span>
                          <span>{tc.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {session.isStreaming && (
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 text-sm font-semibold text-muted-foreground min-w-[60px]">
                ALEC
              </div>
              <div className="flex-1">
                <div className="rounded-lg bg-muted/30 border-l-2 border-muted px-4 py-3">
                  <div className="flex items-center space-x-1.5">
                    <div className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" />
                    <div
                      className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce"
                      style={{ animationDelay: '0.2s' }}
                    />
                    <div
                      className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce"
                      style={{ animationDelay: '0.4s' }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {session.error && (
            <div className="rounded-lg bg-destructive/10 border border-destructive px-4 py-3 text-base text-destructive">
              Error: {session.error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input - Fixed at bottom, centered with max-width */}
      <div className="border-t bg-muted/30">
        <div className="max-w-4xl mx-auto px-8 py-4">
          <form onSubmit={handleSubmit}>
            {/* Message Input */}
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message here..."
                disabled={session.isStreaming}
                className="w-full rounded-lg border border-input bg-background px-4 py-3 pr-12 text-base ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <Button
                type="submit"
                disabled={!input.trim() || session.isStreaming}
                size="icon"
                className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="w-5 h-5"
                >
                  <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
                </svg>
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
