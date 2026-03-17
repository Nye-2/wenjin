"use client";

import { CheckCircle2, FileText, ListChecks, Languages } from "lucide-react";

export interface WorkspaceResultViewModel {
  summary: string;
  sections: { title: string; content: string }[];
  nextActions: string[];
  outputLanguage?: "zh" | "en";
}

interface WorkspaceResultPanelProps {
  viewModel: WorkspaceResultViewModel;
}

export function WorkspaceResultPanel({ viewModel }: WorkspaceResultPanelProps) {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
        <div className="mb-2 flex items-center gap-2">
          <FileText className="h-4 w-4 text-[var(--text-secondary)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">摘要</h3>
          {viewModel.outputLanguage && (
            <span className="ml-auto inline-flex items-center gap-1 rounded-md bg-[var(--bg-elevated)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
              <Languages className="h-3 w-3" />
              {viewModel.outputLanguage.toUpperCase()}
            </span>
          )}
        </div>
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          {viewModel.summary}
        </p>
      </div>

      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
        <div className="mb-3 flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-[var(--text-secondary)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">结构分区</h3>
        </div>
        <div className="space-y-3">
          {viewModel.sections.map((section, index) => (
            <div
              key={`${section.title}-${index}`}
              className="rounded-lg bg-[var(--bg-elevated)] px-3 py-2"
            >
              <p className="text-xs font-medium text-[var(--text-primary)]">
                {section.title}
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                {section.content}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
        <div className="mb-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-[var(--text-secondary)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">下一步动作</h3>
        </div>
        <div className="space-y-2">
          {viewModel.nextActions.map((item, index) => (
            <p
              key={`${item}-${index}`}
              className="text-sm text-[var(--text-secondary)]"
            >
              {index + 1}. {item}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

