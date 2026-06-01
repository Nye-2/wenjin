import {
  Activity,
  CheckCircle2,
  Database,
  History,
  Maximize2,
  Minimize2,
  PauseCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { RunViewStatus } from "@/lib/execution-run-view";
import type { WorkbenchTab } from "@/stores/workbench-layout-store";

import { StatusPill } from "./shared";
import { styles } from "./styles";

const TABS: Array<{
  key: WorkbenchTab;
  label: string;
  icon: LucideIcon;
}> = [
  { key: "overview", label: "总览", icon: Activity },
  { key: "run", label: "运行", icon: History },
  { key: "evidence", label: "证据", icon: Database },
  { key: "review", label: "审阅", icon: CheckCircle2 },
];

export function WorkbenchHeader({
  activeTab,
  status,
  pendingReviewCount,
  evidenceCount,
  sandboxCount,
  isFullscreen,
  canInterrupt,
  interventionOpen,
  interventionStatus,
  onTabChange,
  onToggleFullscreen,
  onToggleIntervention,
}: {
  activeTab: WorkbenchTab;
  status: RunViewStatus | null;
  pendingReviewCount: number;
  evidenceCount: number;
  sandboxCount: number;
  isFullscreen: boolean;
  canInterrupt: boolean;
  interventionOpen: boolean;
  interventionStatus: string | null;
  onTabChange: (tab: WorkbenchTab) => void;
  onToggleFullscreen: () => void;
  onToggleIntervention: () => void;
}) {
  return (
    <div style={styles.header}>
      <div style={{ minWidth: 0 }}>
        <div style={styles.eyebrow}>Agent Workbench</div>
        <div style={styles.headerTitle}>证据化运行工作台</div>
      </div>
      <div style={styles.headerMiddle}>
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const count =
            tab.key === "evidence"
              ? evidenceCount
              : tab.key === "review"
                ? pendingReviewCount
                : tab.key === "run" && sandboxCount > 0
                  ? sandboxCount
                  : 0;
          return (
            <button
              key={tab.key}
              type="button"
              aria-label={tab.label}
              title={tab.label}
              onClick={() => onTabChange(tab.key)}
              style={{
                ...styles.tabButton,
                ...(activeTab === tab.key ? styles.tabButtonActive : null),
                ...(activeTab === tab.key ? styles.tabButtonExpanded : styles.tabButtonIconOnly),
              }}
            >
              <Icon size={14} />
              {activeTab === tab.key ? <span>{tab.label}</span> : null}
              {count > 0 ? <span style={styles.tabBadge}>{Math.min(count, 99)}</span> : null}
            </button>
          );
        })}
      </div>
      <div style={styles.headerActions}>
        {status ? <StatusPill status={status} /> : null}
        <button
          type="button"
          aria-label={interventionOpen ? "收起介入" : "中断并补充"}
          title={interventionOpen ? "收起介入" : "中断并补充"}
          onClick={onToggleIntervention}
          disabled={!canInterrupt}
          style={{
            ...styles.iconTextButton,
            ...(!canInterrupt && !interventionOpen ? styles.iconButtonCompact : null),
            opacity: canInterrupt ? 1 : 0.45,
          }}
        >
          <PauseCircle size={14} />
          {canInterrupt || interventionOpen ? (
            <span>{interventionOpen ? "收起介入" : "中断并补充"}</span>
          ) : null}
        </button>
        <button
          type="button"
          title={isFullscreen ? "退出全屏" : "右侧全屏"}
          aria-label={isFullscreen ? "退出全屏" : "右侧全屏"}
          onClick={onToggleFullscreen}
          style={styles.iconButton}
        >
          {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
        {interventionStatus ? (
          <span style={styles.miniStatus}>{interventionStatus}</span>
        ) : null}
      </div>
    </div>
  );
}
