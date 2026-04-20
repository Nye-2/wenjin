"use client";

import type { Artifact, WorkspaceActivityItem } from "@/stores/workspace";
import {
  DetailFieldGrid,
  DetailSection,
  getActivityMeta,
  getStatusMeta,
  renderStructuredValue,
  resolveMetadataLine,
  resolveSummary,
} from "./WorkspaceKnowledgePanelSupport";

interface WorkspaceActivityDetailSectionsProps {
  selectedActivity: WorkspaceActivityItem;
  selectedActivityFeatureName?: string;
  selectedActivityMeta: Record<string, unknown>;
  selectedActivityArtifact: Artifact | null;
  selectedActivityFollowUpPrompt?: string | null;
  actionError: string | null;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
}

function readTokenCounter(value: unknown): number | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const total = (value as Record<string, unknown>).total_tokens;
  if (typeof total === "number" && Number.isFinite(total)) {
    return Math.max(0, Math.trunc(total));
  }
  if (typeof total === "string") {
    const parsed = Number.parseInt(total.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return null;
}

function readTokenUsage(
  value: unknown
): { input: number; output: number; total: number } | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const payload = value as Record<string, unknown>;
  const inputRaw = payload.input_tokens;
  const outputRaw = payload.output_tokens;
  const totalRaw = payload.total_tokens;
  const input =
    typeof inputRaw === "number"
      ? Math.max(0, Math.trunc(inputRaw))
      : typeof inputRaw === "string"
        ? Math.max(0, Number.parseInt(inputRaw.trim(), 10) || 0)
        : 0;
  const output =
    typeof outputRaw === "number"
      ? Math.max(0, Math.trunc(outputRaw))
      : typeof outputRaw === "string"
        ? Math.max(0, Number.parseInt(outputRaw.trim(), 10) || 0)
        : 0;
  const parsedTotal =
    typeof totalRaw === "number"
      ? Math.max(0, Math.trunc(totalRaw))
      : typeof totalRaw === "string"
        ? Math.max(0, Number.parseInt(totalRaw.trim(), 10) || 0)
        : 0;
  const total = parsedTotal > 0 ? parsedTotal : input + output;
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return { input, output, total };
}

function FeatureTaskSections({
  selectedActivity,
  selectedActivityMeta,
  selectedActivityFollowUpPrompt,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivity" | "selectedActivityMeta" | "selectedActivityFollowUpPrompt"
>) {
  const taskTokenUsage = readTokenUsage(selectedActivityMeta.token_usage);
  const subagentCount =
    typeof selectedActivityMeta.subagent_count === "number"
      ? selectedActivityMeta.subagent_count
      : null;
  return (
    <>
      <DetailSection title="执行状态">
        <DetailFieldGrid
          fields={[
            [
              "进度",
              `${typeof selectedActivityMeta.progress === "number" ? selectedActivityMeta.progress : 0}%`,
            ],
            [
              "当前步骤",
              typeof selectedActivityMeta.current_step === "string"
                ? selectedActivityMeta.current_step
                : "未提供",
            ],
            [
              "反馈消息",
              typeof selectedActivityMeta.message === "string"
                ? selectedActivityMeta.message
                : selectedActivity.status === "failed"
                  ? "执行失败"
                  : "无",
            ],
            [
              "开始时间",
              typeof selectedActivityMeta.started_at === "string"
                ? new Date(selectedActivityMeta.started_at).toLocaleString("zh-CN")
                : "未开始",
            ],
            [
              "结束时间",
              typeof selectedActivityMeta.completed_at === "string"
                ? new Date(selectedActivityMeta.completed_at).toLocaleString("zh-CN")
                : "未结束",
            ],
            [
              "动作",
              typeof selectedActivityMeta.action === "string"
                ? selectedActivityMeta.action
                : "默认动作",
            ],
            [
              "执行累计 tokens",
              taskTokenUsage ? taskTokenUsage.total.toLocaleString() : "未知",
            ],
            [
              "Token 明细",
              taskTokenUsage
                ? `输入 ${taskTokenUsage.input.toLocaleString()} / 输出 ${taskTokenUsage.output.toLocaleString()}`
                : "未知",
            ],
            [
              "子代理数量",
              typeof subagentCount === "number" ? subagentCount : "未知",
            ],
          ]}
        />
      </DetailSection>

      {selectedActivityMeta.params && typeof selectedActivityMeta.params === "object" && (
        <DetailSection title="输入参数">
          {renderStructuredValue(selectedActivityMeta.params)}
        </DetailSection>
      )}

      {selectedActivityMeta.result && (
        <DetailSection title="执行结果">
          {renderStructuredValue(selectedActivityMeta.result)}
        </DetailSection>
      )}

      {selectedActivityFollowUpPrompt && selectedActivityFollowUpPrompt.trim() && (
        <DetailSection title="建议下一步">
          <p className="text-sm leading-6 text-[var(--text-primary)]">
            {selectedActivityFollowUpPrompt}
          </p>
        </DetailSection>
      )}

      {typeof selectedActivityMeta.error === "string" && selectedActivityMeta.error && (
        <DetailSection title="错误信息">
          <p className="text-sm leading-6 text-red-600">{selectedActivityMeta.error}</p>
        </DetailSection>
      )}
    </>
  );
}

function ThreadSection({
  selectedActivity,
  selectedActivityMeta,
  resolveSkillLabel,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivity" | "selectedActivityMeta" | "resolveSkillLabel"
>) {
  const threadTokenUsage = readTokenCounter(selectedActivityMeta.thread_token_usage);
  const lastMessageTokenUsage = readTokenCounter(
    selectedActivityMeta.last_message_token_usage
  );
  return (
    <DetailSection title="会话上下文">
      <DetailFieldGrid
        fields={[
          [
            "能力",
            selectedActivity.skill_name ||
              (typeof selectedActivityMeta.skill_name === "string"
                ? selectedActivityMeta.skill_name
                : null) ||
              (typeof selectedActivity.skill === "string"
                ? resolveSkillLabel(selectedActivity.skill)
                : typeof selectedActivityMeta.skill === "string"
                  ? resolveSkillLabel(selectedActivityMeta.skill)
                  : null) ||
              (typeof selectedActivity.skill === "string"
                ? selectedActivity.skill
                : typeof selectedActivityMeta.skill === "string"
                  ? selectedActivityMeta.skill
                  : null) ||
              "未设置",
          ],
          [
            "消息数",
            typeof selectedActivityMeta.message_count === "number"
              ? selectedActivityMeta.message_count
              : "未知",
          ],
          [
            "最后一条角色",
            typeof selectedActivityMeta.last_message_role === "string"
              ? selectedActivityMeta.last_message_role
              : "未知",
          ],
          [
            "会话累计 tokens",
            typeof threadTokenUsage === "number"
              ? threadTokenUsage.toLocaleString()
              : "未知",
          ],
          [
            "最后一条 tokens",
            typeof lastMessageTokenUsage === "number"
              ? lastMessageTokenUsage.toLocaleString()
              : "未知",
          ],
        ]}
      />
    </DetailSection>
  );
}

function SubagentTaskSections({
  selectedActivity,
  selectedActivityMeta,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivity" | "selectedActivityMeta"
>) {
  const tokenUsage = readTokenUsage(selectedActivityMeta.token_usage);
  const modelName =
    typeof selectedActivityMeta.model_name === "string"
      ? selectedActivityMeta.model_name
      : null;
  return (
    <>
      <DetailSection title="子代理上下文">
        <DetailFieldGrid
          fields={[
            ["代理类型", selectedActivity.title || "未指定"],
            ["Thread ID", selectedActivity.thread_id || "无"],
            ["状态", getStatusMeta(selectedActivity.status)?.label || "无"],
            [
              "累计 tokens",
              tokenUsage ? tokenUsage.total.toLocaleString() : "未知",
            ],
            [
              "Token 明细",
              tokenUsage
                ? `输入 ${tokenUsage.input.toLocaleString()} / 输出 ${tokenUsage.output.toLocaleString()}`
                : "未知",
            ],
            ["模型", modelName || "未知"],
          ]}
        />
      </DetailSection>

      {typeof selectedActivityMeta.prompt === "string" && (
        <DetailSection title="任务 Prompt">
          <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-primary)]">
            {selectedActivityMeta.prompt}
          </p>
        </DetailSection>
      )}

      {typeof selectedActivityMeta.output_preview === "string" &&
        selectedActivityMeta.output_preview && (
          <DetailSection title="输出摘要">
            <p className="text-sm leading-6 text-[var(--text-primary)]">
              {selectedActivityMeta.output_preview}
            </p>
          </DetailSection>
        )}

      {typeof selectedActivityMeta.error === "string" && selectedActivityMeta.error && (
        <DetailSection title="错误信息">
          <p className="text-sm leading-6 text-red-600">{selectedActivityMeta.error}</p>
        </DetailSection>
      )}
    </>
  );
}

function ArtifactSections({
  selectedActivity,
  selectedActivityMeta,
  selectedActivityArtifact,
  resolveSkillLabel,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  | "selectedActivity"
  | "selectedActivityMeta"
  | "selectedActivityArtifact"
  | "resolveSkillLabel"
>) {
  return (
    <>
      <DetailSection title="产出信息">
        <DetailFieldGrid
          fields={[
            [
              "产出类型",
              typeof selectedActivityMeta.artifact_type === "string"
                ? selectedActivityMeta.artifact_type.replace(/[_-]/g, " ")
                : "未知",
            ],
            [
              "版本",
              typeof selectedActivityMeta.version === "number"
                ? selectedActivityMeta.version
                : "未知",
            ],
            [
              "创建技能",
              selectedActivity.created_by_skill_name ||
              (typeof selectedActivityMeta.created_by_skill_name === "string"
                ? selectedActivityMeta.created_by_skill_name
                : null) ||
              (typeof selectedActivity.created_by_skill === "string"
                ? resolveSkillLabel(selectedActivity.created_by_skill)
                : typeof selectedActivityMeta.created_by_skill === "string"
                  ? resolveSkillLabel(selectedActivityMeta.created_by_skill)
                  : null) ||
              (typeof selectedActivity.created_by_skill === "string"
                ? selectedActivity.created_by_skill
                : typeof selectedActivityMeta.created_by_skill === "string"
                  ? selectedActivityMeta.created_by_skill
                  : null) ||
              "未知",
            ],
          ]}
        />
      </DetailSection>

      {selectedActivityArtifact && (
        <DetailSection title="内容预览">
          {renderStructuredValue(selectedActivityArtifact.content)}
        </DetailSection>
      )}
    </>
  );
}

export function WorkspaceActivityDetailSections({
  selectedActivity,
  selectedActivityFeatureName,
  selectedActivityMeta,
  selectedActivityArtifact,
  selectedActivityFollowUpPrompt,
  actionError,
  resolveSkillLabel,
}: WorkspaceActivityDetailSectionsProps) {
  return (
    <div className="space-y-4">
      <DetailSection title="概览">
        <DetailFieldGrid
          fields={[
            [
              "活动类型",
              getActivityMeta(selectedActivity, selectedActivityArtifact).label,
            ],
            ["状态", getStatusMeta(selectedActivity.status)?.label || "无"],
            [
              "发生时间",
              new Date(selectedActivity.occurred_at).toLocaleString("zh-CN"),
            ],
            ["关联模块", selectedActivityFeatureName || "未关联模块"],
            ["Thread ID", selectedActivity.thread_id || "无"],
            ["Task ID", selectedActivity.task_id || "无"],
          ]}
        />
      </DetailSection>

      <DetailSection title="摘要">
        <p className="text-sm leading-6 text-[var(--text-primary)]">
          {resolveSummary(selectedActivity)}
        </p>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {resolveMetadataLine(
            selectedActivity,
            selectedActivityFeatureName,
            resolveSkillLabel
          )}
        </p>
      </DetailSection>

      {actionError && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          {actionError}
        </div>
      )}

      {selectedActivity.kind === "feature_task" && (
        <FeatureTaskSections
          selectedActivity={selectedActivity}
          selectedActivityMeta={selectedActivityMeta}
          selectedActivityFollowUpPrompt={selectedActivityFollowUpPrompt}
        />
      )}

      {selectedActivity.kind === "thread" && (
        <ThreadSection
          selectedActivity={selectedActivity}
          selectedActivityMeta={selectedActivityMeta}
          resolveSkillLabel={resolveSkillLabel}
        />
      )}

      {selectedActivity.kind === "subagent_task" && (
        <SubagentTaskSections
          selectedActivity={selectedActivity}
          selectedActivityMeta={selectedActivityMeta}
        />
      )}

      {selectedActivity.kind === "artifact" && (
        <ArtifactSections
          selectedActivity={selectedActivity}
          selectedActivityMeta={selectedActivityMeta}
          selectedActivityArtifact={selectedActivityArtifact}
          resolveSkillLabel={resolveSkillLabel}
        />
      )}
    </div>
  );
}
