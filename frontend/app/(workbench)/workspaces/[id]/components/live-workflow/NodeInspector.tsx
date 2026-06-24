import {
  Activity,
  FlaskConical,
  Info,
  ShieldCheck,
} from "lucide-react";

import type { ExecutionNodeState } from "@/lib/api/types";
import { executionNodeDisplayName } from "@/lib/execution-run-view";

import { EmptyState, InspectorBlock, NodeStatusDot } from "./shared";
import { styles } from "./styles";
import {
  buildSandboxSummary,
  formatDateTime,
  readString,
  statusLabel,
  truncate,
} from "./utils";

export function NodeInspector({
  node,
  state,
}: {
  node: { id: string; type?: string; label?: string; task?: string } | null;
  state: ExecutionNodeState | null;
}) {
  if (!node && !state) {
    return <EmptyState title="选择步骤" detail="这里会显示当前步骤的进展摘要、状态和可安全展示的运行线索。" compact />;
  }
  const sandboxSummary = buildSandboxSummary(state);
  const title = executionNodeDisplayName(
    node
      ? {
          id: node.id,
          type: node.type ?? "node",
          label: node.label,
          task: node.task,
        }
      : null,
    state,
  );
  return (
    <div style={styles.nodeInspector}>
      <div style={styles.sectionTitle}>{title}</div>
      <div style={styles.nodeMetaLine}>
        <NodeStatusDot status={state?.status ?? "pending"} />
        <span>{statusLabel(state?.status ?? "pending")}</span>
      </div>

      {state?.thinking ? (
        <InspectorBlock title="进展摘要" icon={Activity}>
          {truncate(state.thinking, 360)}
        </InspectorBlock>
      ) : (
        <InspectorBlock title="进展摘要" icon={Info}>
          当前步骤暂无详细摘要。
        </InspectorBlock>
      )}

      <details style={styles.debugDetails}>
        <summary style={styles.debugSummary}>技术详情</summary>
        <div style={styles.debugStack}>
          <InspectorBlock title="技术标识" icon={Info}>
            <div style={styles.sandboxSummary}>
              <div>{node?.id ?? "unknown"}</div>
              {state?.started_at ? <div>启动时间：{formatDateTime(state.started_at)}</div> : null}
            </div>
          </InspectorBlock>
          {state?.tool_calls && state.tool_calls.length > 0 ? (
            <InspectorBlock title="工具调用" icon={ShieldCheck}>
              <div style={styles.toolList}>
                {state.tool_calls.slice(0, 6).map((call, index) => (
                  <div key={index} style={styles.toolItem}>
                    <span style={styles.toolName}>{readString(call.name) ?? `tool-${index + 1}`}</span>
                    <span style={styles.toolMeta}>
                      {[
                        readString(call.status),
                        call.exit_code !== undefined ? `exit ${String(call.exit_code)}` : null,
                        readString(call.docker_image),
                      ].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                ))}
              </div>
            </InspectorBlock>
          ) : null}
          {sandboxSummary ? (
            <InspectorBlock title="实验环境摘要" icon={FlaskConical}>
              <div style={styles.sandboxSummary}>
                {sandboxSummary.map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </div>
            </InspectorBlock>
          ) : null}
        </div>
      </details>
    </div>
  );
}
