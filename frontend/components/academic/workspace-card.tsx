"use client";

import { motion } from "framer-motion";
import { FileText, Book, FileEdit, Lightbulb, Sigma } from "lucide-react";
import type { WorkspaceType } from "@/lib/workspace-types";

interface WorkspaceCardProps {
  id: string;
  name: string;
  type: WorkspaceType;
  discipline?: string;
  referenceCount: number;
  artifactCount: number;
  createdAt: string;
}

const typeIcons = {
  sci: FileText,
  thesis: Book,
  proposal: FileEdit,
  software_copyright: FileText,
  math_modeling: Sigma,
  patent: Lightbulb,
};

const typeLabels = {
  sci: "SCI Paper",
  thesis: "Undergraduate Thesis",
  proposal: "Project Application",
  software_copyright: "Software Copyright",
  math_modeling: "Mathematical Modeling",
  patent: "Patent Application",
};

const typeColors = {
  sci: { bg: "bg-[var(--wjn-accent-soft)]", text: "text-[var(--wjn-blue)]" },
  thesis: { bg: "bg-[var(--wjn-evidence-soft)]", text: "text-[var(--wjn-evidence)]" },
  proposal: { bg: "bg-[var(--wjn-review-soft)]", text: "text-[var(--wjn-review)]" },
  software_copyright: { bg: "bg-[var(--wjn-surface-subtle)]", text: "text-[var(--wjn-text-secondary)]" },
  math_modeling: { bg: "bg-[var(--wjn-evidence-soft)]", text: "text-[var(--wjn-evidence)]" },
  patent: { bg: "bg-[rgba(231,176,8,0.12)]", text: "text-[var(--wjn-review)]" },
};

const typeBadgeColors = {
  sci: "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue-strong)]",
  thesis: "border-[rgba(15,118,110,0.24)] bg-[var(--wjn-evidence-soft)] text-[var(--wjn-evidence)]",
  proposal: "border-[rgba(180,83,9,0.24)] bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]",
  software_copyright: "border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-secondary)]",
  math_modeling: "border-[rgba(15,118,110,0.24)] bg-[var(--wjn-evidence-soft)] text-[var(--wjn-evidence)]",
  patent: "border-[rgba(231,176,8,0.24)] bg-[rgba(231,176,8,0.10)] text-[var(--wjn-review)]",
};

export function WorkspaceCard({
  id,
  name,
  type,
  discipline,
  referenceCount,
  artifactCount,
  createdAt,
}: WorkspaceCardProps) {
  const Icon = typeIcons[type];

  return (
    <motion.a href={`/workspaces/${id}`} className="block h-full">
      <div className="h-full cursor-pointer rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-6 shadow-[var(--wjn-shadow-sm)] transition-[border-color,box-shadow,transform] duration-150 ease-[var(--wjn-ease-standard)] hover:-translate-y-px hover:border-[var(--wjn-accent-line)] hover:shadow-[var(--wjn-shadow-md)]">
        <div className="flex items-start justify-between mb-4">
          <div className={`rounded-[var(--wjn-radius-lg)] p-2.5 ${typeColors[type].bg} ${typeColors[type].text}`}>
            <Icon className="w-5 h-5" />
          </div>
          <span className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${typeBadgeColors[type]}`}>
            {typeLabels[type]}
          </span>
        </div>

        <h3 className="mb-2 line-clamp-2 text-lg font-semibold leading-tight text-[var(--wjn-text)]">
          {name}
        </h3>

        {discipline && (
          <p className="mb-4 text-sm text-[var(--wjn-text-secondary)]">
            {discipline.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </p>
        )}

        <div className="flex items-center gap-4 text-sm text-[var(--wjn-text-muted)]">
          <span className="flex items-center gap-1.5">
            <FileText className="w-4 h-4" />
            {referenceCount} references
          </span>
          <span className="flex items-center gap-1.5">
            <Book className="w-4 h-4" />
            {artifactCount} artifacts
          </span>
        </div>

        <div className="mt-4 border-t border-[var(--wjn-line)] pt-4">
          <p className="text-xs text-[var(--wjn-text-muted)]">
            Created {createdAt}
          </p>
        </div>
      </div>
    </motion.a>
  );
}
