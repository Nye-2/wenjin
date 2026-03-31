"use client";

import { ArrowRight, CheckCircle2, FileText, Languages, ListChecks } from "lucide-react";

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
    <div className="mx-auto w-full max-w-4xl space-y-5">
      <div className="route-card rounded-[1.75rem] p-6">
        <div className="mb-3 flex items-center gap-2">
          <FileText className="h-4 w-4 text-[var(--brand-brass)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">结果摘要</h3>
          {viewModel.outputLanguage && (
            <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-[11px] text-[var(--text-muted)]">
              <Languages className="h-3 w-3" />
              {viewModel.outputLanguage.toUpperCase()}
            </span>
          )}
        </div>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {viewModel.summary}
        </p>
      </div>

      <div className="route-card rounded-[1.75rem] p-6">
        <div className="mb-3 flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-[var(--brand-navy)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">结构分区</h3>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {viewModel.sections.map((section, index) => (
            <div
              key={`${section.title}-${index}`}
              className="rounded-2xl border border-[var(--border-default)] bg-white/78 px-4 py-3"
            >
              <p className="text-xs font-medium text-[var(--text-primary)]">
                {section.title}
              </p>
              <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
                {section.content}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="route-card rounded-[1.75rem] p-6">
        <div className="mb-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-[var(--brand-teal)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">建议下一步</h3>
        </div>
        <div className="space-y-3">
          {viewModel.nextActions.map((item, index) => (
            <div
              key={`${item}-${index}`}
              className="flex items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-white/76 px-4 py-3"
            >
              <span className="mt-0.5 rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--accent-primary)]">
                {index + 1}
              </span>
              <p className="flex-1 text-sm leading-7 text-[var(--text-secondary)]">
                {item}
              </p>
              <ArrowRight className="mt-1 h-4 w-4 text-[var(--text-muted)]" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
