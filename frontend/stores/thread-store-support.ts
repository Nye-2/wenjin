import {
  type ThreadAttachment,
  type ThreadMessage,
  type ThreadMessageBlock,
  type ExecutionSession,
  type Thread,
  type ThreadSummary,
  type WorkspaceTaskEvent,
} from "@/lib/api";
import { useExecutionStore } from "@/stores/execution";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocks: ThreadMessageBlock[];
  metadata: Record<string, unknown> | null;
  pending?: boolean;
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
    nextMessages[lastIndex] = message;
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

export function findLastAssistantMessage(
  messages: Message[]
): Message | undefined {
  return [...messages].reverse().find((message) => message.role === "assistant");
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

export function syncAttachmentExtractionsWithTask(
  messages: Message[],
  task: WorkspaceTaskEvent["task"]
): Message[] {
  if (!task.thread_id) {
    return messages;
  }

  let changed = false;

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
      const extraction =
        metadata?.extraction && typeof metadata.extraction === "object"
          ? { ...(metadata.extraction as Record<string, unknown>) }
          : null;

      if (!metadata || !extraction || extraction.task_id !== task.task_id) {
        return attachment;
      }

      extraction.status = task.status;
      extraction.progress = task.progress;
      extraction.current_step = task.current_step ?? null;
      extraction.message =
        task.error || task.message || (typeof extraction.message === "string" ? extraction.message : null);
      if (task.error) {
        extraction.error = task.error;
      } else if (task.status === "success") {
        delete extraction.error;
      }

      metadata.extraction = extraction;
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

function readStructuredExecutionDescriptor(
  message: Message
): {
  featureId: string;
  taskId: string | null;
  executionSessionId: string | null;
  params: Record<string, unknown>;
  status: string | null;
} | null {
  const orchestration = message.metadata?.orchestration;
  if (!orchestration || typeof orchestration !== "object") {
    return null;
  }

  const orchestrationData = orchestration as Record<string, unknown>;
  const taskId =
    typeof orchestrationData.task_id === "string"
      ? orchestrationData.task_id
      : null;
  const executionSessionId =
    typeof orchestrationData.execution_session_id === "string"
      ? orchestrationData.execution_session_id
      : null;
  const featureId =
    typeof orchestrationData.feature_id === "string"
      ? orchestrationData.feature_id
      : null;
  const params =
    orchestrationData.params && typeof orchestrationData.params === "object"
      ? (orchestrationData.params as Record<string, unknown>)
      : {};
  const status =
    typeof orchestrationData.status === "string"
      ? orchestrationData.status
      : null;

  if (!featureId || (!taskId && !executionSessionId)) {
    return null;
  }

  return {
    featureId,
    taskId,
    executionSessionId,
    params,
    status,
  };
}

function buildPlaceholderExecutionSession(options: {
  descriptor: NonNullable<ReturnType<typeof readStructuredExecutionDescriptor>>;
  message: Message;
  workspaceId?: string | null;
}): ExecutionSession {
  const { descriptor, message, workspaceId } = options;
  const createdAt = message.created_at || new Date().toISOString();
  return {
    id: descriptor.executionSessionId || descriptor.taskId || `exec-${descriptor.featureId}`,
    user_id: "",
    workspace_id: workspaceId || "",
    thread_id: null,
    workspace_type: "",
    feature_id: descriptor.featureId,
    entry_skill_id: null,
    launch_source: "thread",
    launch_message: message.content || null,
    status:
      descriptor.status === "completed"
        ? "completed"
        : descriptor.status === "failed"
          ? "failed"
          : descriptor.status === "awaiting_user_input"
            ? "awaiting_user_input"
          : descriptor.status === "warning"
            ? "advisory"
            : "pending",
    params: descriptor.params,
    task_ids: descriptor.taskId ? [descriptor.taskId] : [],
    primary_task_id: descriptor.taskId,
    runtime_snapshot: null,
    progress: null,
    task_message: message.content || null,
    current_step: null,
    result_payload: null,
    subagents: [],
    result_summary: message.content || null,
    artifact_ids: [],
    next_actions: [],
    advisory_code: null,
    last_error: null,
    created_at: createdAt,
    updated_at: createdAt,
    started_at: null,
    completed_at: null,
  };
}

export function maybeHydrateStructuredExecution(
  message: Message,
  workspaceId?: string | null
) {
  const descriptor = readStructuredExecutionDescriptor(message);
  if (!descriptor) {
    return;
  }
  const normalizedWorkspaceId = String(workspaceId ?? "").trim();
  if (!normalizedWorkspaceId) {
    return;
  }

  const executionStore = useExecutionStore.getState();
  const executionId = descriptor.executionSessionId || descriptor.taskId;
  if (!executionId) {
    return;
  }

  const executions = executionStore.byWorkspace[normalizedWorkspaceId] ?? [];
  if (executions.some((item) => item.id === executionId)) {
    return;
  }

  executionStore.upsertExecution(
    normalizedWorkspaceId,
    buildPlaceholderExecutionSession({
      descriptor,
      message,
      workspaceId: normalizedWorkspaceId,
    })
  );
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
