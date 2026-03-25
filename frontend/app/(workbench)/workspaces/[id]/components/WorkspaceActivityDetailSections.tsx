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
  actionError: string | null;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
}

function FeatureTaskSections({
  selectedActivity,
  selectedActivityMeta,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivity" | "selectedActivityMeta"
>) {
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

      {typeof selectedActivityMeta.error === "string" && selectedActivityMeta.error && (
        <DetailSection title="错误信息">
          <p className="text-sm leading-6 text-red-600">{selectedActivityMeta.error}</p>
        </DetailSection>
      )}
    </>
  );
}

function ChatThreadSection({
  selectedActivityMeta,
  resolveSkillLabel,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivityMeta" | "resolveSkillLabel"
>) {
  return (
    <DetailSection title="会话上下文">
      <DetailFieldGrid
        fields={[
          [
            "能力",
            typeof selectedActivityMeta.skill === "string"
              ? resolveSkillLabel(selectedActivityMeta.skill) || "未设置"
              : "未设置",
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
  return (
    <>
      <DetailSection title="子代理上下文">
        <DetailFieldGrid
          fields={[
            ["代理类型", selectedActivity.title || "未指定"],
            ["Thread ID", selectedActivity.thread_id || "无"],
            ["状态", getStatusMeta(selectedActivity.status)?.label || "无"],
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
  selectedActivityMeta,
  selectedActivityArtifact,
}: Pick<
  WorkspaceActivityDetailSectionsProps,
  "selectedActivityMeta" | "selectedActivityArtifact"
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
              typeof selectedActivityMeta.created_by_skill === "string"
                ? selectedActivityMeta.created_by_skill
                : "未知",
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
        />
      )}

      {selectedActivity.kind === "chat_thread" && (
        <ChatThreadSection
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
          selectedActivityMeta={selectedActivityMeta}
          selectedActivityArtifact={selectedActivityArtifact}
        />
      )}
    </div>
  );
}
