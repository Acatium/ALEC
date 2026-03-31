/**
 * Message input component
 */

import { useState, useCallback, type FormEvent, type KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { SendIcon } from '@/components/ui/Icons';

export interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

function MessageInput({
  onSend,
  disabled = false,
  placeholder = 'Type your message...',
  className,
}: MessageInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const trimmed = message.trim();
      if (trimmed && !disabled) {
        onSend(trimmed);
        setMessage('');
      }
    },
    [message, disabled, onSend]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const trimmed = message.trim();
        if (trimmed && !disabled) {
          onSend(trimmed);
          setMessage('');
        }
      }
    },
    [message, disabled, onSend]
  );

  return (
    <form onSubmit={handleSubmit} className={cn('flex gap-2', className)}>
      <div className="relative flex-1">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={cn(
            'w-full resize-none rounded-lg border border-gray-300 bg-white px-4 py-3 pr-12 text-sm',
            'placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'dark:border-gray-700 dark:bg-gray-800 dark:placeholder:text-gray-400'
          )}
          style={{ minHeight: '48px', maxHeight: '200px' }}
        />
      </div>
      <Button
        type="submit"
        variant="primary"
        size="icon"
        disabled={disabled || !message.trim()}
        className="h-12 w-12 shrink-0"
        aria-label="Send message"
      >
        <SendIcon className="h-5 w-5" />
      </Button>
    </form>
  );
}

export { MessageInput };
