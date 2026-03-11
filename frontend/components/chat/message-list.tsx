'use client';

import { useRef, useEffect, useState, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User, Bot, Sparkles, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
  skill?: string;
}

interface MessageListProps {
  messages: Message[];
  isStreaming?: boolean;
  streamingContent?: string;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded-md hover:bg-[var(--bg-surface)] transition-colors"
      title="Copy message"
      aria-label="Copy message"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-[var(--semantic-success)]" />
      ) : (
        <Copy className="h-3.5 w-3.5 text-[var(--text-muted)]" />
      )}
    </button>
  );
}

const MessageBubble = memo(function MessageBubble({
  message,
  isLast,
  isStreaming,
}: {
  message: Message;
  isLast: boolean;
  isStreaming?: boolean;
}) {
  const isUser = message.role === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn('flex gap-3 group', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser
            ? 'bg-[var(--accent-primary)] text-white'
            : 'bg-gradient-to-br from-[var(--accent-secondary)] to-purple-600 text-white'
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Message Content */}
      <div className={cn('flex-1 max-w-[85%] flex flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-3 relative',
            isUser
              ? 'bg-[var(--accent-primary)] text-white rounded-tr-sm'
              : 'bg-[var(--bg-surface)] text-[var(--text-primary)] rounded-tl-sm border border-[var(--border-default)]'
          )}
        >
          {isLast && !isUser && isStreaming ? (
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-[var(--accent-secondary)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-[var(--accent-secondary)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-[var(--accent-secondary)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-[var(--text-muted)]">Thinking...</span>
            </div>
          ) : (
            <div className="text-sm whitespace-pre-wrap prose prose-sm max-w-none">
              {message.content}
            </div>
          )}
        </div>

        {/* Meta info and actions */}
        <div
          className={cn(
            'flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity',
            isUser ? 'flex-row-reverse' : 'flex-row'
          )}
        >
          {!isUser && <CopyButton text={message.content} />}
          {message.skill && (
            <span className="text-xs text-[var(--text-muted)] px-2 py-0.5 rounded-full bg-[var(--bg-surface)]">
              {message.skill}
            </span>
          )}
          {message.created_at && (
            <span className="text-xs text-[var(--text-muted)]">
              {new Date(message.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
});

export function MessageList({ messages, isStreaming, streamingContent }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  if (messages.length === 0) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-[var(--accent-secondary)] to-purple-600 flex items-center justify-center">
            <Sparkles className="w-8 h-8 text-white" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
            Start Your Research Journey
          </h3>
          <p className="text-sm text-[var(--text-secondary)]">
            Select a skill below and ask me anything about your research. I can help
            with literature reviews, paper writing, experiment design, and more.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex-1 overflow-y-auto p-6 space-y-4"
      role="log"
      aria-live="polite"
      aria-label="Chat messages"
      tabIndex={0}
    >
      <AnimatePresence mode="popLayout">
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            isLast={index === messages.length - 1}
            isStreaming={isStreaming && index === messages.length - 1 && message.role === 'assistant'}
          />
        ))}
      </AnimatePresence>

      {/* Streaming content */}
      {streamingContent && (
        <MessageBubble
          message={{
            id: 'streaming',
            role: 'assistant',
            content: streamingContent,
          }}
          isLast={true}
          isStreaming={false}
        />
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
