'use client';

import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Send, Paperclip, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface MessageInputProps {
  onSend: (message: string) => void;
  isDisabled?: boolean;
  isStreaming?: boolean;
  onStop?: () => void;
  placeholder?: string;
}

export function MessageInput({
  onSend,
  isDisabled = false,
  isStreaming = false,
  onStop,
  placeholder = 'Ask about your research...',
}: MessageInputProps) {
  const [inputValue, setInputValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [inputValue]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isDisabled || isStreaming) return;

    onSend(inputValue.trim());
    setInputValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="p-4 border-t border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
      <form onSubmit={handleSubmit} className="flex gap-3 items-end">
        {/* Attachment button (future feature) */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface)]"
          title="Attach file (coming soon)"
          disabled
        >
          <Paperclip className="h-5 w-5" />
        </Button>

        {/* Text input */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isDisabled}
            rows={1}
            className={cn(
              'w-full px-4 py-3 rounded-xl resize-none',
              'bg-[var(--bg-surface)] backdrop-blur-sm',
              'border border-[var(--border-default)] focus:border-[var(--border-focus)]',
              'text-[var(--text-primary)] placeholder:text-[var(--text-muted)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20',
              'transition-all duration-200',
              isDisabled && 'opacity-50 cursor-not-allowed'
            )}
          />
        </div>

        {/* Send/Stop button */}
        {isStreaming ? (
          <motion.button
            type="button"
            onClick={onStop}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className={cn(
              'px-4 py-3 rounded-xl flex items-center justify-center',
              'bg-[var(--semantic-error)] text-white',
              'hover:opacity-90 transition-colors'
            )}
          >
            <Square className="h-5 w-5" />
          </motion.button>
        ) : (
          <motion.button
            type="submit"
            disabled={!inputValue.trim() || isDisabled}
            whileHover={{ scale: inputValue.trim() ? 1.02 : 1 }}
            whileTap={{ scale: inputValue.trim() ? 0.98 : 1 }}
            className={cn(
              'px-4 py-3 rounded-xl flex items-center justify-center',
              'bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white',
              'hover:shadow-lg transition-all',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Send className="h-5 w-5" />
          </motion.button>
        )}
      </form>

      {/* Helper text */}
      <div className="flex items-center justify-between mt-2 px-1">
        <p className="text-xs text-[var(--text-muted)]">
          Press <kbd className="px-1.5 py-0.5 rounded bg-[var(--bg-surface)] text-[var(--text-secondary)]">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 rounded bg-[var(--bg-surface)] text-[var(--text-secondary)]">Shift+Enter</kbd> for new line
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          {inputValue.length} characters
        </p>
      </div>
    </div>
  );
}
