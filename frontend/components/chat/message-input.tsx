'use client';

import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Send, Paperclip, Mic, Square } from 'lucide-react';
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
    <div className="p-4 border-t border-slate-700/50 bg-slate-800/50 backdrop-blur-xl">
      <form onSubmit={handleSubmit} className="flex gap-3 items-end">
        {/* Attachment button (future feature) */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="flex-shrink-0 text-slate-400 hover:text-white hover:bg-slate-700"
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
              'bg-slate-900/50 backdrop-blur-sm',
              'border border-slate-600 focus:border-blue-500/50',
              'text-white placeholder:text-slate-500',
              'focus:outline-none focus:ring-2 focus:ring-blue-500/20',
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
              'bg-red-600 text-white',
              'hover:bg-red-700 transition-colors'
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
              'bg-blue-600 text-white',
              'hover:bg-blue-700 transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-600'
            )}
          >
            <Send className="h-5 w-5" />
          </motion.button>
        )}
      </form>

      {/* Helper text */}
      <div className="flex items-center justify-between mt-2 px-1">
        <p className="text-xs text-slate-500">
          Press <kbd className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">Shift+Enter</kbd> for new line
        </p>
        <p className="text-xs text-slate-500">
          {inputValue.length} characters
        </p>
      </div>
    </div>
  );
}
