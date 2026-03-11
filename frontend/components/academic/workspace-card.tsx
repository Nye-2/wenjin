"use client";

import { motion } from "framer-motion";
import { FileText, Book, FileEdit, DollarSign } from "lucide-react";
import { LiquidGlassCard } from "@/components/glass";

interface WorkspaceCardProps {
  id: string;
  name: string;
  type: "sci" | "thesis" | "proposal" | "software_copyright" | "patent";
  discipline?: string;
  paperCount: number;
  artifactCount: number;
  createdAt: string;
}

const typeIcons = {
  sci: FileText,
  thesis: Book,
  proposal: FileEdit,
  grant: DollarSign,
  software_copyright: FileText,
  patent: Lightbulb,
};

const typeLabels = {
  sci: "SCI Paper",
  thesis: "Undergraduate Thesis",
  proposal: "Project Application",
  software_copyright: "Software Copyright",
  patent: "Patent Application",
};

const typeColors = {
  sci: { bg: "bg-[#1E3A8A]", text: "text-white" },
  thesis: { bg: "bg-[#7C3AED]", text: "text-white" },
  proposal: { bg: "bg-[#059669]", text: "text-white" },
  software_copyright: { bg: "bg-[#8B5CF6]", text: "text-white" },
  patent: { bg: "bg-[#EC4899]", text: "text-white" },
};

const typeBadgeColors = {
  sci: "bg-[#1E3A8A]/10 text-[#1E3A8A]",
  thesis: "bg-[#7C3AED]/10 text-[#7C3AED]",
  proposal: "bg-[#059669]/10 text-[#059669]",
  software_copyright: "bg-[#8B5CF6]/10 text-[#8B5CF6]",
  patent: "bg-[#EC4899]/10 text-[#EC4899]",
};

export function WorkspaceCard({
  id,
  name,
  type,
  discipline,
  paperCount,
  artifactCount,
  createdAt,
}: WorkspaceCardProps) {
  const Icon = typeIcons[type];

  return (
    <motion.a href={`/workspaces/${id}`} className="block h-full">
      <LiquidGlassCard
        variant="floating"
        className="p-6 cursor-pointer h-full hover:border-[var(--accent-primary)]/30"
      >
        <div className="flex items-start justify-between mb-4">
          <div className={`p-2.5 rounded-xl ${typeColors[type].bg} ${typeColors[type].text}`}>
            <Icon className="w-5 h-5" />
          </div>
          <span className={`text-xs font-semibold px-3 py-1.5 rounded-full ${typeBadgeColors[type]}`}>
            {typeLabels[type]}
          </span>
        </div>

        <h3 className="font-semibold text-lg mb-2 text-[var(--text-primary)] line-clamp-2 leading-tight">
          {name}
        </h3>

        {discipline && (
          <p className="text-sm text-[var(--text-secondary)] mb-4">
            {discipline.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </p>
        )}

        <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
          <span className="flex items-center gap-1.5">
            <FileText className="w-4 h-4" />
            {paperCount} papers
          </span>
          <span className="flex items-center gap-1.5">
            <Book className="w-4 h-4" />
            {artifactCount} artifacts
          </span>
        </div>

        <div className="mt-4 pt-4 border-t border-[var(--border-default)]">
          <p className="text-xs text-[var(--text-muted)]">
            Created {createdAt}
          </p>
        </div>
      </LiquidGlassCard>
    </motion.a>
  );
}
