"use client";

import { motion } from "framer-motion";
import { FileText, Book, FileEdit, DollarSign } from "lucide-react";
import { LiquidGlassCard } from "@/components/glass";

interface WorkspaceCardProps {
  id: string;
  name: string;
  type: "sci" | "thesis" | "proposal" | "grant";
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
};

const typeLabels = {
  sci: "SCI Paper",
  thesis: "Graduate Thesis",
  proposal: "Research Proposal",
  grant: "Grant Application",
};

const typeColors = {
  sci: "bg-blue-500",
  thesis: "bg-purple-500",
  proposal: "bg-green-500",
  grant: "bg-amber-500",
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
    <motion.a href={`/workspaces/${id}`}>
      <LiquidGlassCard
        variant="floating"
        className="p-6 cursor-pointer h-full"
      >
        <div className="flex items-start justify-between mb-4">
          <div className={`p-2 rounded-lg ${typeColors[type]}`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
          <span className="text-xs font-medium px-2 py-1 rounded-full bg-academic-primary/10 text-academic-primary">
            {typeLabels[type]}
          </span>
        </div>

        <h3 className="font-semibold text-lg mb-2 line-clamp-2">{name}</h3>

        {discipline && (
          <p className="text-sm text-muted-foreground mb-4">
            {discipline.replace("_", " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </p>
        )}

        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <FileText className="w-4 h-4" />
            {paperCount} papers
          </span>
          <span className="flex items-center gap-1">
            <Book className="w-4 h-4" />
            {artifactCount} artifacts
          </span>
        </div>

        <div className="mt-4 pt-4 border-t border-border/50">
          <p className="text-xs text-muted-foreground">
            Created {createdAt}
          </p>
        </div>
      </LiquidGlassCard>
    </motion.a>
  );
}
