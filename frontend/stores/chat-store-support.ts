import {
  type ChatAttachment,
  type ChatMessage,
  type ChatMessageBlock,
  type Thread,
  type ThreadSummary,
  type WorkspaceTaskEvent,
} from "@/lib/api";
import { trackWorkspaceFeatureTask } from "@/lib/workspace-feature-execution";
import { useFeaturesStore } from "@/stores/features";
import { useTaskStore } from "@/stores/task";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocks: ChatMessageBlock[];
  metadata: Record<string, unknown> | null;
}

export function createPendingUserMessage(options: {
  id: string;
  content: string;
  createdAt: string;
  attachments?: ChatAttachment[];
}): Message {
  return {
    id: options.id,
    role: "user",
    content: options.content,
    created_at: options.createdAt,
    blocks: [],
    metadata:
      options.attachments && options.attachments.length > 0
        ? { attachments: options.attachments }
        : null,
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

export function createStoreAssistantMessage(options: {
  fallbackId: string;
  fallbackCreatedAt: string;
  message: ChatMessage;
}): Message {
  const { fallbackId, fallbackCreatedAt, message } = options;
  return {
    id: fallbackId,
    role: message.role === "user" ? "user" : "assistant",
    content: message.content,
    created_at: message.timestamp ?? fallbackCreatedAt,
    blocks: Array.isArray(message.blocks) ? message.blocks : [],
    metadata: message.metadata ?? null,
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

function readStructuredTaskDescriptor(
  message: Message
): { featureId: string; taskId: string } | null {
  const orchestration = message.metadata?.orchestration;
  if (!orchestration || typeof orchestration !== "object") {
    return null;
  }

  const orchestrationData = orchestration as Record<string, unknown>;
  const taskId =
    typeof orchestrationData.task_id === "string"
      ? orchestrationData.task_id
      : null;
  const featureId =
    typeof orchestrationData.feature_id === "string"
      ? orchestrationData.feature_id
      : null;

  if (!taskId || !featureId) {
    return null;
  }

  return { featureId, taskId };
}

export function maybeStartStructuredTask(message: Message) {
  const descriptor = readStructuredTaskDescriptor(message);
  if (!descriptor) {
    return;
  }

  const featuresStore = useFeaturesStore.getState();
  const feature = featuresStore.getFeatureById(descriptor.featureId);
  if (!feature) {
    return;
  }

  const taskStore = useTaskStore.getState();
  if (taskStore.currentTask?.id === descriptor.taskId) {
    return;
  }

  trackWorkspaceFeatureTask({
    feature,
    startTask: taskStore.startTask,
    taskId: descriptor.taskId,
    initialThinking: message.content,
  });
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
  messageCount: number;
  createdAt: string;
}): ThreadSummary {
  return {
    id: options.threadId,
    workspace_id: options.workspaceId,
    title: null,
    model: options.model ?? "default",
    skill: options.skill,
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
      created_at: thread.created_at,
      updated_at: thread.updated_at,
      ...buildThreadPreview(thread.messages),
    };
  }

  return thread;
}
