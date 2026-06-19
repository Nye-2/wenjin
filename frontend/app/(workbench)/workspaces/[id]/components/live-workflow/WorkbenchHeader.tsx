import {
  Activity,
  CheckCircle2,
  Database,
  History,
  MoreHorizontal,
  Maximize2,
  Minimize2,
  PauseCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { WorkbenchTab } from "@/stores/workbench-layout-store";

import { styles } from "./styles";

const TABS: Array<{
  key: WorkbenchTab;
  label: string;
  icon: LucideIcon;
  primary?: boolean;
}> = [
  { key: "overview", label: "总览", icon: Activity, primary: true },
  { key: "evidence", label: "证据", icon: Database, primary: true },
  { key: "review", label: "待确认", icon: CheckCircle2, primary: true },
  { key: "run", label: "进展", icon: History },
];

export function WorkbenchHeader({
  activeTab,
  pendingReviewCount,
  evidenceCount,
  showProgressTab,
  hasRunHistory,
  isFullscreen,
  canInterrupt,
  interventionOpen,
  interventionStatus,
  onTabChange,
  onToggleFullscreen,
  onToggleIntervention,
}: {
  activeTab: WorkbenchTab;
  pendingReviewCount: number;
  evidenceCount: number;
  showProgressTab: boolean;
  hasRunHistory: boolean;
  isFullscreen: boolean;
  canInterrupt: boolean;
  interventionOpen: boolean;
  interventionStatus: string | null;
  onTabChange: (tab: WorkbenchTab) => void;
  onToggleFullscreen: () => void;
  onToggleIntervention: () => void;
}) {
  const visibleTabs = TABS.filter((tab) => tab.primary || showProgressTab || activeTab === tab.key);
  return (
    <div style={styles.header}>
      <div style={{ minWidth: 0 }}>
        <div style={styles.eyebrow}>Research Workbench</div>
        <div style={styles.headerTitle}>研究工作台</div>
      </div>
      <div style={styles.headerMiddle}>
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          const count =
            tab.key === "evidence"
              ? evidenceCount
              : tab.key === "review"
                ? pendingReviewCount
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
        {hasRunHistory && !showProgressTab && activeTab !== "run" ? (
          <button
            type="button"
            aria-label="更多运行诊断"
            title="更多运行诊断"
            onClick={() => onTabChange("run")}
            style={{
              ...styles.tabButton,
              ...styles.tabButtonIconOnly,
            }}
          >
            <MoreHorizontal size={14} />
          </button>
        ) : null}
      </div>
      <div style={styles.headerActions}>
        {canInterrupt || interventionOpen ? (
          <button
            type="button"
            aria-label={interventionOpen ? "收起介入" : "中断并补充"}
            title={interventionOpen ? "收起介入" : "中断并补充"}
            onClick={onToggleIntervention}
            disabled={!canInterrupt && !interventionOpen}
            style={{
              ...styles.iconTextButton,
              opacity: canInterrupt || interventionOpen ? 1 : 0.45,
            }}
          >
            <PauseCircle size={14} />
            <span>{interventionOpen ? "收起介入" : "中断并补充"}</span>
          </button>
        ) : null}
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
