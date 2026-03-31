/**
 * Message list component
 */

import type { RefObject } from 'react';
import { cn } from '@/lib/utils';
import { Message, type MessageProps } from './Message';
import { EmptyState } from '@/components/shared/EmptyState';
import { MessageSquareIcon } from '@/components/ui/Icons';

export interface MessageListProps {
  messages: MessageProps[];
  messagesEndRef?: RefObject<HTMLDivElement>;
  className?: string;
}

function MessageList({ messages, messagesEndRef, className }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className={cn('flex flex-1 items-center justify-center', className)}>
        <EmptyState
          icon={<MessageSquareIcon className="h-12 w-12" />}
          title="Start a conversation"
          description="Send a message to begin chatting with ALEC"
        />
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col gap-4 overflow-y-auto p-4', className)}>
      {messages.map((message, index) => (
        <Message key={message.isOptimistic ? `optimistic-${index}` : index} {...message} />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
}

export { MessageList };
