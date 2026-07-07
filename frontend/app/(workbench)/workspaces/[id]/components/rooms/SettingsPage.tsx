"use client";

import { useEffect, useState } from "react";
import { DecisionsViewer } from "./DecisionsViewer";
import { SettingsForm } from "./SettingsForm";

interface SettingsPageProps {
  workspaceId: string;
  open: boolean;
  defaultTab?: TabKey;
  onClose: () => void;
}

type TabKey = "decisions" | "settings";

const TABS: { key: TabKey; label: string }[] = [
  { key: "decisions", label: "Decisions" },
  { key: "settings", label: "Settings" },
];

export function SettingsPage({
  workspaceId,
  open,
  defaultTab,
  onClose,
}: SettingsPageProps) {
  const [visible, setVisible] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>(defaultTab ?? "decisions");

  useEffect(() => {
    if (!defaultTab) {
      return;
    }
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setActiveTab(defaultTab);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [defaultTab]);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setVisible(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  if (!open) return null;

  return (
    <div
      style={{
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: 560,
        background: "var(--wjn-surface)",
        borderLeft: "1px solid rgba(20, 20, 30, 0.08)",
        boxShadow: "var(--wjn-shadow-md)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 13,
      }}
      data-testid="settings-page"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            fontSize: 15,
            color: "var(--wjn-text)",
          }}
        >
          Settings
        </span>
        <button
          onClick={handleClose}
          data-testid="settings-close"
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            fontSize: 16,
            color: "var(--wjn-text-muted)",
            lineHeight: 1,
            padding: 4,
          }}
        >
          ✕
        </button>
      </div>

      {/* Tab bar */}
      <div
        data-testid="settings-tabs"
        style={{
          display: "flex",
          borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
          padding: "0 16px",
        }}
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              data-testid={`tab-${tab.key}`}
              style={{
                border: "none",
                background: "transparent",
                cursor: "pointer",
                padding: "10px 16px",
                fontSize: 13,
                fontWeight: isActive ? 600 : 400,
                color: isActive
                  ? "var(--wjn-blue)"
                  : "var(--wjn-text-muted)",
                borderBottom: isActive
                  ? "2px solid var(--wjn-blue)"
                  : "2px solid transparent",
                fontFamily: "var(--wjn-font-sans)",
                transition: "color 150ms, border-color 150ms",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {activeTab === "decisions" && (
          <DecisionsViewer workspaceId={workspaceId} />
        )}
        {activeTab === "settings" && (
          <SettingsForm workspaceId={workspaceId} />
        )}
      </div>
    </div>
  );
}
