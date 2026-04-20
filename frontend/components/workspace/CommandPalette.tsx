"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Compass,
  FileJson,
  FileText,
  Keyboard,
  Search,
} from "lucide-react";

import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { exportConversationAsJson, exportConversationAsMarkdown } from "@/lib/thread-export";
import { useThreadStore } from "@/stores/thread";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface CommandPaletteProps {
  workspaceId: string;
}

interface CommandAction {
  id: string;
  title: string;
  description: string;
  section: "通用" | "模块" | "会话";
  shortcut?: string;
  keywords: string[];
  perform: () => void;
  icon: typeof Compass;
}

export function CommandPalette({ workspaceId }: CommandPaletteProps) {
  const router = useRouter();
  const messages = useThreadStore((state) => state.messages);
  const currentThreadSummary = useThreadStore(
    (state) => state.currentThreadSummary
  );
  const [open, setOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [query, setQuery] = useState("");

  const isMac =
    typeof navigator !== "undefined" && navigator.userAgent.toLowerCase().includes("mac");
  const metaLabel = isMac ? "⌘" : "Ctrl+";
  const currentThread = currentThreadSummary;

  const baseActions: CommandAction[] = [
    {
      id: "workspace-overview",
      title: "打开工作台总览",
      description: "返回 workspace 主界面，查看线程、模块和知识面板。",
      section: "通用",
      keywords: ["workspace", "overview", "thread", "总览", "主页"],
      perform: () => router.push(`/workspaces/${workspaceId}`),
      icon: Compass,
    },
    {
      id: "shortcut-help",
      title: "查看快捷键",
      description: "打开快捷键帮助面板。",
      section: "通用",
      shortcut: `${metaLabel}/`,
      keywords: ["shortcut", "keyboard", "help", "快捷键", "帮助"],
      perform: () => setHelpOpen(true),
      icon: Keyboard,
    },
  ];

  const exportActions: CommandAction[] =
    currentThread && messages.length > 0
      ? [
          {
            id: "export-markdown",
            title: "导出当前会话为 Markdown",
            description: "导出适合留档和评审阅读的对话记录。",
            section: "会话",
            keywords: ["export", "markdown", "conversation", "导出", "会话"],
            perform: () => exportConversationAsMarkdown(currentThread, messages),
            icon: FileText,
          },
          {
            id: "export-json",
            title: "导出当前会话为 JSON",
            description: "导出完整结构化会话数据。",
            section: "会话",
            keywords: ["export", "json", "conversation", "导出", "会话"],
            perform: () => exportConversationAsJson(currentThread, messages),
            icon: FileJson,
          },
        ]
      : [];

  const actions = [...baseActions, ...exportActions];
  const normalizedQuery = query.trim().toLowerCase();
  const filteredActions = actions.filter((action) => {
    if (!normalizedQuery) {
      return true;
    }
    return [action.title, action.description, ...action.keywords]
      .join(" ")
      .toLowerCase()
      .includes(normalizedQuery);
  });

  useGlobalShortcuts([
    {
      key: "k",
      meta: true,
      action: () => {
        setHelpOpen(false);
        setOpen((current) => !current);
      },
    },
    {
      key: "/",
      meta: true,
      action: () => {
        setOpen(false);
        setHelpOpen(true);
      },
    },
  ]);

  const runAction = (action: CommandAction) => {
    action.perform();
    setOpen(false);
    setQuery("");
  };

  const sections: Array<CommandAction["section"]> = ["通用", "会话"];

  return (
    <>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl gap-3">
          <DialogHeader>
            <DialogTitle>命令面板</DialogTitle>
            <DialogDescription>
              直接搜索会话动作和常用导航，不必在页面里来回找入口。
            </DialogDescription>
          </DialogHeader>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <Input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && filteredActions.length > 0) {
                  event.preventDefault();
                  runAction(filteredActions[0]);
                }
              }}
              placeholder="搜索会话动作或导航..."
              className="pl-10"
            />
          </div>
          <div className="max-h-[55vh] overflow-y-auto">
            {filteredActions.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[var(--border-default)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">
                没有匹配项，试试导出、对话或总览等关键词。
              </div>
            ) : (
              <div className="space-y-4">
                {sections.map((section) => {
                  const sectionActions = filteredActions.filter(
                    (action) => action.section === section
                  );
                  if (sectionActions.length === 0) {
                    return null;
                  }
                  return (
                    <div key={section}>
                      <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-muted)]">
                        {section}
                      </p>
                      <div className="space-y-2">
                        {sectionActions.map((action, index) => {
                          const Icon = action.icon;
                          return (
                            <button
                              key={action.id}
                              type="button"
                              onClick={() => runAction(action)}
                              className={cn(
                                "flex w-full items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-left transition-colors hover:bg-[var(--bg-muted)]",
                                index === 0 && "border-[var(--accent-primary)]/35"
                              )}
                            >
                              <span className="mt-0.5 rounded-lg bg-[var(--bg-muted)] p-2 text-[var(--text-primary)]">
                                <Icon className="h-4 w-4" />
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="flex items-center justify-between gap-3">
                                  <span className="text-sm font-medium text-[var(--text-primary)]">
                                    {action.title}
                                  </span>
                                  {action.shortcut ? (
                                    <span className="rounded-md bg-[var(--bg-muted)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                                      {action.shortcut}
                                    </span>
                                  ) : null}
                                </span>
                                <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
                                  {action.description}
                                </span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>快捷键</DialogTitle>
            <DialogDescription>
              当前工作区下最常用的键盘入口。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {[
              { keys: `${metaLabel}K`, label: "打开命令面板" },
              { keys: `${metaLabel}/`, label: "打开快捷键说明" },
            ].map((item) => (
              <div
                key={item.keys}
                className="flex items-center justify-between rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2"
              >
                <span className="text-sm text-[var(--text-primary)]">{item.label}</span>
                <span className="rounded-md bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-muted)]">
                  {item.keys}
                </span>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
