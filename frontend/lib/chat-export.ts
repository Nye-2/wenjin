import type { ThreadSummary, Workspace } from "@/lib/api";
import type { Message } from "@/stores/chat";

interface ExportableThread extends Partial<ThreadSummary> {
  id: string;
  workspace_type?: Workspace["type"] | null;
}

function sanitizeFilenameSegment(value: string | null | undefined): string {
  const normalized = (value || "").trim().replace(/\s+/g, "-");
  const sanitized = normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/-+/g, "-");
  return sanitized.replace(/^[-_.]+|[-_.]+$/g, "") || "conversation";
}

function resolveConversationSkillLabel(thread: ExportableThread): string | null {
  const skillId = thread.skill?.trim();
  if (!skillId) {
    return null;
  }
  return skillId.replace(/[-_]/g, " ");
}

function resolveConversationTitle(thread: ExportableThread): string {
  const explicitTitle = thread.title?.trim();
  if (explicitTitle) {
    return explicitTitle;
  }
  const skillLabel = resolveConversationSkillLabel(thread);
  if (skillLabel) {
    return skillLabel;
  }
  return `Conversation ${thread.id.slice(0, 8)}`;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN");
}

function serializeBlocks(message: Message): string[] {
  if (!Array.isArray(message.blocks) || message.blocks.length === 0) {
    return [];
  }

  const lines = ["### Structured Blocks"];
  for (const block of message.blocks) {
    const label = block.title?.trim() || block.type;
    lines.push(`- ${label}`);
    if (block.data && Object.keys(block.data).length > 0) {
      lines.push("");
      lines.push("```json");
      lines.push(JSON.stringify(block.data, null, 2));
      lines.push("```");
    }
  }
  return lines;
}

function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function buildFilename(thread: ExportableThread, extension: "md" | "json"): string {
  const title = sanitizeFilenameSegment(resolveConversationTitle(thread));
  const threadId = sanitizeFilenameSegment(thread.id);
  return `${title}-${threadId}.${extension}`;
}

export function formatConversationAsMarkdown(
  thread: ExportableThread,
  messages: Message[],
): string {
  const title = resolveConversationTitle(thread);
  const skillLabel = resolveConversationSkillLabel(thread);
  const lines: string[] = [
    `# ${title}`,
    "",
    `- Thread ID: ${thread.id}`,
    `- Workspace ID: ${thread.workspace_id || "N/A"}`,
    `- Model: ${thread.model || "default"}`,
    `- Skill: ${skillLabel || thread.skill || "N/A"}`,
    `- Exported At: ${formatTimestamp(new Date().toISOString())}`,
    "",
    "---",
    "",
  ];

  for (const message of messages) {
    const roleLabel = message.role === "user" ? "User" : "Assistant";
    lines.push(`## ${roleLabel}`);
    lines.push(`- Timestamp: ${formatTimestamp(message.created_at)}`);
    lines.push("");
    lines.push(message.content?.trim() || "_Empty message_");
    lines.push("");
    const blockLines = serializeBlocks(message);
    if (blockLines.length > 0) {
      lines.push(...blockLines);
      lines.push("");
    }
    lines.push("---");
    lines.push("");
  }

  return lines.join("\n");
}

export function exportConversationAsMarkdown(
  thread: ExportableThread,
  messages: Message[],
) {
  const filename = buildFilename(thread, "md");
  const markdown = formatConversationAsMarkdown(thread, messages);
  downloadTextFile(filename, markdown, "text/markdown;charset=utf-8");
}

export function exportConversationAsJson(
  thread: ExportableThread,
  messages: Message[],
) {
  const filename = buildFilename(thread, "json");
  const payload = {
    thread: {
      id: thread.id,
      title: thread.title || null,
      workspace_id: thread.workspace_id || null,
      model: thread.model || "default",
      skill: thread.skill || null,
      updated_at: thread.updated_at || null,
    },
    exported_at: new Date().toISOString(),
    messages,
  };
  downloadTextFile(
    filename,
    JSON.stringify(payload, null, 2),
    "application/json;charset=utf-8",
  );
}
