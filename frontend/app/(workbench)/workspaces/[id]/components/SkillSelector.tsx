"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  BookOpen,
  FileText,
  ListOrdered,
  PenTool,
  FlaskConical,
  Lightbulb,
} from "lucide-react";
import type { Workspace } from "@/lib/api";
import { getWorkspaceChatSkills } from "@/lib/workspace-chat-skills";
import { cn } from "@/lib/utils";

const skillIcons = {
  search: Search,
  list: ListOrdered,
  file: FileText,
  book: BookOpen,
  pen: PenTool,
  flask: FlaskConical,
  lightbulb: Lightbulb,
} as const;

interface SkillSelectorProps {
  workspaceType?: Workspace["type"] | null;
  selectedSkill?: string | null;
  onSelect: (skillId: string | null) => void;
}

export function SkillSelector({
  workspaceType,
  selectedSkill,
  onSelect,
}: SkillSelectorProps) {
  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null);
  const skills = getWorkspaceChatSkills(workspaceType);

  if (skills.length === 0) {
    return null;
  }

  const handleSelect = (skillId: string) => {
    if (selectedSkill === skillId) {
      onSelect(null); // Deselect if already selected
    } else {
      onSelect(skillId);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {skills.map((skill) => {
        const Icon = skillIcons[skill.icon];
        const isSelected = selectedSkill === skill.id;
        const isHovered = hoveredSkill === skill.id;

        return (
          <div key={skill.id} className="relative">
            <motion.button
              onClick={() => handleSelect(skill.id)}
              onMouseEnter={() => setHoveredSkill(skill.id)}
              onMouseLeave={() => setHoveredSkill(null)}
              className={cn(
                "relative px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200",
                "border border-[var(--border-default)]",
                isSelected
                  ? "bg-[var(--accent-primary)] text-white border-[var(--accent-primary)]"
                  : cn(
                      "bg-[var(--bg-surface)]",
                      "hover:bg-[var(--bg-muted)]",
                      skill.colorClass
                    )
              )}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full",
                    isSelected ? "bg-white/15" : skill.backgroundClass
                  )}
                >
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5",
                      isSelected ? "text-white" : skill.colorClass
                    )}
                  />
                </span>
                {skill.name}
              </span>
            </motion.button>

            {/* Tooltip */}
            <AnimatePresence>
              {isHovered && !isSelected && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  className={cn(
                    "absolute left-0 right-0 top-full mt-2 p-2 rounded-lg z-50",
                    "bg-[var(--text-primary)] text-white text-xs",
                    "shadow-lg border border-white/10",
                    "whitespace-nowrap"
                  )}
                >
                  {skill.description}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
