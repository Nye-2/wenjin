import {
  Activity,
  ClipboardList,
  Database,
  FlaskConical,
  ShieldCheck,
} from "lucide-react";

import type { ExecutionNodeState } from "@/lib/api/types";

import { EmptyState, InspectorBlock, NodeStatusDot } from "./shared";
import { styles } from "./styles";
import {
  buildSandboxSummary,
  formatDateTime,
  formatJsonPreview,
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
    return <EmptyState title="选择节点" detail="节点详情会显示输入、输出、工具调用和 sandbox 摘要。" compact />;
  }
  const output = state?.output ?? null;
  const sandboxSummary = buildSandboxSummary(state);
  return (
    <div style={styles.nodeInspector}>
      <div style={styles.sectionTitle}>{node?.label ?? node?.task ?? node?.id ?? "节点详情"}</div>
      <div style={styles.nodeMetaLine}>
        <NodeStatusDot status={state?.status ?? "pending"} />
        <span>{statusLabel(state?.status ?? "pending")}</span>
        {state?.started_at ? <span>{formatDateTime(state.started_at)}</span> : null}
      </div>

      {state?.thinking ? (
        <InspectorBlock title="进展摘要" icon={Activity}>
          {truncate(state.thinking, 360)}
        </InspectorBlock>
      ) : null}
      {state?.input ? (
        <InspectorBlock title="输入预览" icon={ClipboardList}>
          <pre style={styles.pre}>{formatJsonPreview(state.input)}</pre>
        </InspectorBlock>
      ) : null}
      {output ? (
        <InspectorBlock title="输出预览" icon={Database}>
          <pre style={styles.pre}>{formatJsonPreview(output)}</pre>
        </InspectorBlock>
      ) : null}
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
        <InspectorBlock title="Sandbox 摘要" icon={FlaskConical}>
          <div style={styles.sandboxSummary}>
            {sandboxSummary.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        </InspectorBlock>
      ) : null}
    </div>
  );
}
