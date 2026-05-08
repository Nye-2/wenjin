import {
  type ThreadAttachment,
  type ThreadMessage,
  type ThreadMessageBlock,
  type Thread,
  type ThreadSummary,
  type WorkspaceTaskEvent,
} from "@/lib/api";
import type { AgentBlock } from "@/lib/api/blocks";
import type { ChatMessage } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocks: ThreadMessageBlock[];
  agentBlocks?: AgentBlock[];
  run_id?: string | null;
  metadata: Record<string, unknown> | null;
  pending?: boolean;
}

function blockRunId(block: AgentBlock): string | null {
  if (block.kind === "status_line" || block.kind === "result_card") {
    return block.run_id;
  }
  return null;
}

export function appendAgentBlock(
  messages: Message[],
  messageId: string,
  block: AgentBlock,
): Message[] {
  const existing = messages.findIndex((m) => m.id === messageId);
  if (existing >= 0) {
    return messages.map((m, i) =>
      i === existing
        ? {
            ...m,
            agentBlocks: [...(m.agentBlocks ?? []), block],
            run_id: m.run_id ?? blockRunId(block),
            pending: false,
          }
        : m,
    );
  }

  const lastIndex = messages.length - 1;
  const last = messages[lastIndex];
  if (last && last.role === "assistant" && last.pending) {
    return messages.map((m, i) =>
      i === lastIndex
        ? {
            ...m,
            id: messageId,
            agentBlocks: [block],
            run_id: blockRunId(block),
            content: "",
            pending: false,
          }
        : m,
    );
  }

  return [
    ...messages,
    {
      id: messageId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      blocks: [],
      agentBlocks: [block],
      run_id: blockRunId(block),
      metadata: null,
      pending: false,
    },
  ];
}

export function toChatMessages(messages: Message[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  for (let i = 0; i < messages.length; i += 1) {
    const m = messages[i]!;
    if (m.role === "user") {
      let runId: string | null = m.run_id ?? null;
      if (!runId) {
        for (let j = i + 1; j < messages.length; j += 1) {
          const next = messages[j]!;
          if (next.role === "assistant" && next.run_id) {
            runId = next.run_id;
            break;
          }
        }
      }
      out.push({
        id: m.id,
        role: "user",
        run_id: runId ?? `local:user:${m.id}`,
        text: m.content,
      });
      continue;
    }

    const agentBlocks = m.agentBlocks ?? [];
    const blocks: AgentBlock[] =
      agentBlocks.length > 0
        ? agentBlocks
        : m.content
          ? [{ kind: "text", content: m.content }]
          : [];
    if (blocks.length === 0 && m.pending) {
      continue;
    }
    out.push({
      id: m.id,
      role: "agent",
      run_id: m.run_id ?? `local:assistant:${m.id}`,
      blocks,
    });
  }
  return out;
}

export function createPendingUserMessage(options: {
  id: string;
  content: string;
  createdAt: string;
  attachments?: ThreadAttachment[];
  metadata?: Record<string, unknown>;
}): Message {
  const metadata =
    options.attachments && options.attachments.length > 0
      ? { ...(options.metadata ?? {}), attachments: options.attachments }
      : options.metadata ?? null;
  return {
    id: options.id,
    role: "user",
    content: options.content,
    created_at: options.createdAt,
    blocks: [],
    metadata,
    pending: false,
  };
}

export function createPlaceholderAssistantMessage(options: {
  id: string;
  createdAt: string;
}): Message {
  return {
    id: options.id,
    role: "assistant",
    content: "",
    created_at: options.createdAt,
    blocks: [],
    metadata: null,
    pending: true,
  };
}

export function appendAssistantContent(
  messages: Message[],
  content: string
): Message[] {
  const nextMessages = [...messages];
  const lastIndex = nextMessages.length - 1;
  if (lastIndex >= 0 && nextMessages[lastIndex].role === "assistant") {
    nextMessages[lastIndex] = {
      ...nextMessages[lastIndex],
      content,
    };
  }
  return nextMessages;
}

function buildReasoningBlock(text: string): ThreadMessageBlock {
  return {
    type: "reasoning",
    title: "思考过程",
    data: { text },
  };
}

export function upsertTrailingAssistantReasoning(
  messages: Message[],
  reasoning: string
): Message[] {
  const nextMessages = [...messages];
  const lastIndex = nextMessages.length - 1;
  if (lastIndex < 0 || nextMessages[lastIndex].role !== "assistant") {
    return messages;
  }

  const nextBlocks = [...nextMessages[lastIndex].blocks];
  const reasoningBlockIndex = nextBlocks.findIndex(
    (block) => block.type === "reasoning"
  );
  const reasoningBlock = buildReasoningBlock(reasoning);

  if (reasoningBlockIndex >= 0) {
    nextBlocks[reasoningBlockIndex] = reasoningBlock;
  } else {
    nextBlocks.unshift(reasoningBlock);
  }

  nextMessages[lastIndex] = {
    ...nextMessages[lastIndex],
    blocks: nextBlocks,
  };
  return nextMessages;
}

export function createStoreAssistantMessage(options: {
  fallbackId: string;
  fallbackCreatedAt: string;
  message: ThreadMessage;
}): Message {
  const { fallbackId, fallbackCreatedAt, message } = options;
  return {
    id: fallbackId,
    role: message.role === "user" ? "user" : "assistant",
    content: message.content,
    created_at: message.timestamp ?? fallbackCreatedAt,
    blocks: Array.isArray(message.blocks) ? message.blocks : [],
    metadata: message.metadata ?? null,
    pending: false,
  };
}

export function upsertTrailingAssistantMessage(
  messages: Message[],
  message: Message
): Message[] {
  const nextMessages = [...messages];
  const lastIndex = nextMessages.length - 1;
  if (lastIndex >= 0 && nextMessages[lastIndex].role === "assistant") {
    const old = nextMessages[lastIndex];
    // Preserve agentBlocks from streaming — the server's ThreadMessage
    // has content (plain text) but not the structured AgentBlock array
    // that was assembled during SSE block events.
    nextMessages[lastIndex] = {
      ...message,
      agentBlocks: old.agentBlocks?.length
        ? old.agentBlocks
        : message.agentBlocks,
    };
  } else {
    nextMessages.push(message);
  }
  return nextMessages;
}

export function removeTrailingEmptyAssistantMessage(
  messages: Message[]
): Message[] {
  const lastMessage = messages[messages.length - 1];
  if (
    !lastMessage ||
    lastMessage.role !== "assistant" ||
    lastMessage.content.trim().length > 0 ||
    lastMessage.blocks.length > 0 ||
    lastMessage.metadata
  ) {
    return messages;
  }
  return messages.slice(0, -1);
}

export function removeTrailingPendingAssistantMessage(
  messages: Message[]
): Message[] {
  const lastMessage = messages[messages.length - 1];
  if (!lastMessage || lastMessage.role !== "assistant" || !lastMessage.pending) {
    return messages;
  }
  return messages.slice(0, -1);
}

export function toStoreMessages(detail: Thread): Message[] {
  return detail.messages
    .filter(
      (message): message is typeof message & { role: "user" | "assistant" } =>
        message.role === "user" || message.role === "assistant"
    )
    .map((message, index) => ({
      id: `${detail.id}:${index}`,
      role: message.role,
      content: message.content,
      created_at: message.timestamp ?? detail.updated_at,
      blocks: Array.isArray(message.blocks) ? message.blocks : [],
      metadata: message.metadata ?? null,
      pending: false,
    }));
}

export function syncAttachmentPreprocessWithTask(
  messages: Message[],
  task: WorkspaceTaskEvent["task"]
): Message[] {
  if (!task.thread_id) {
    return messages;
  }

  let changed = false;
  const rawResultPreprocess = task.result?.["preprocess"];
  const resultPreprocess =
    rawResultPreprocess && typeof rawResultPreprocess === "object"
      ? (rawResultPreprocess as Record<string, unknown>)
      : null;

  const nextMessages = messages.map((message) => {
    const attachments = message.metadata?.attachments;
    if (!Array.isArray(attachments) || attachments.length === 0) {
      return message;
    }

    let messageChanged = false;
    const nextAttachments = attachments.map((attachment) => {
      if (!attachment || typeof attachment !== "object") {
        return attachment;
      }

      const attachmentRecord = attachment as Record<string, unknown>;
      const metadata =
        attachmentRecord.metadata && typeof attachmentRecord.metadata === "object"
          ? { ...(attachmentRecord.metadata as Record<string, unknown>) }
          : null;
      const preprocess =
        metadata?.preprocess && typeof metadata.preprocess === "object"
          ? { ...(metadata.preprocess as Record<string, unknown>) }
          : null;

      if (!metadata || !preprocess || preprocess.task_id !== task.task_id) {
        return attachment;
      }

      if (resultPreprocess) {
        Object.assign(preprocess, resultPreprocess);
      }
      preprocess.task_id = task.task_id;
      if (task.status === "failed") {
        preprocess.status = "failed";
      } else if (task.status === "success") {
        preprocess.status =
          typeof preprocess.status === "string" ? preprocess.status : "succeeded";
      } else if (task.status === "running" || task.status === "pending") {
        preprocess.status = task.status;
      }
      preprocess.progress = task.progress;
      preprocess.current_step = task.current_step ?? null;
      preprocess.message =
        task.error ||
        task.message ||
        (typeof preprocess.message === "string" ? preprocess.message : null);
      if (task.error) {
        preprocess.error = task.error;
      } else if (task.status === "success" && preprocess.status === "succeeded") {
        delete preprocess.error;
      }

      metadata.preprocess = preprocess;
      if (Array.isArray(preprocess.markdown_paths) && preprocess.markdown_paths.length > 0) {
        metadata.preprocessed_markdown_paths = preprocess.markdown_paths;
      }
      messageChanged = true;
      changed = true;
      return {
        ...attachmentRecord,
        metadata,
      };
    });

    if (!messageChanged) {
      return message;
    }

    return {
      ...message,
      metadata: {
        ...(message.metadata ?? {}),
        attachments: nextAttachments,
      },
    };
  });

  return changed ? nextMessages : messages;
}

function buildThreadPreview(messages: Thread["messages"]) {
  const lastMessage = messages[messages.length - 1];
  const normalizedPreview =
    typeof lastMessage?.content === "string"
      ? lastMessage.content.replace(/\s+/g, " ").trim()
      : "";

  return {
    message_count: messages.length,
    last_message_role: lastMessage?.role ?? null,
    last_message_preview: normalizedPreview
      ? normalizedPreview.length <= 120
        ? normalizedPreview
        : `${normalizedPreview.slice(0, 117).trimEnd()}...`
      : null,
  };
}

export function buildPendingThreadSummary(options: {
  threadId: string;
  workspaceId?: string;
  model?: string;
  skill: string | null;
  skillName?: string | null;
  messageCount: number;
  createdAt: string;
}): ThreadSummary {
  return {
    id: options.threadId,
    workspace_id: options.workspaceId,
    title: null,
    model: options.model ?? "default",
    skill: options.skill,
    skill_name: options.skillName ?? null,
    message_count: options.messageCount,
    last_message_role: "assistant",
    last_message_preview: null,
    created_at: options.createdAt,
    updated_at: options.createdAt,
  };
}

export function toThreadSummary(thread: Thread | ThreadSummary): ThreadSummary {
  if ("messages" in thread) {
    return {
      id: thread.id,
      workspace_id: thread.workspace_id,
      title: thread.title ?? null,
      model: thread.model,
      skill: thread.skill ?? null,
      skill_name: thread.skill_name ?? null,
      created_at: thread.created_at,
      updated_at: thread.updated_at,
      ...buildThreadPreview(thread.messages),
    };
  }

  return thread;
}
