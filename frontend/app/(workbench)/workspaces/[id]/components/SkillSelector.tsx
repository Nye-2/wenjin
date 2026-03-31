"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { iconMap, defaultIcon } from "@/lib/icon-map";
import { useFeaturesStore } from "@/stores/features";
import { cn } from "@/lib/utils";

const colorClassMap: Record<string, { text: string; bg: string }> = {
  navy: { text: "text-[var(--brand-navy)]", bg: "bg-[rgba(31,66,99,0.08)]" },
  teal: { text: "text-[var(--brand-teal)]", bg: "bg-[rgba(46,111,109,0.08)]" },
  cyan: { text: "text-[var(--brand-cyan)]", bg: "bg-[rgba(92,151,165,0.08)]" },
  brass: {
    text: "text-[var(--brand-brass)]",
    bg: "bg-[rgba(166,124,57,0.08)]",
  },
  slate: {
    text: "text-[var(--text-secondary)]",
    bg: "bg-[rgba(120,135,139,0.08)]",
  },
};

const defaultColor = { text: "text-[var(--text-secondary)]", bg: "bg-[rgba(120,135,139,0.08)]" };

interface SkillSelectorProps {
  selectedSkill: string | null;
  onSelect: (skillId: string | null) => void;
}

export function SkillSelector({
  selectedSkill,
  onSelect,
}: SkillSelectorProps) {
  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null);
  const skills = useFeaturesStore((state) => state.skills);

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
        const Icon = iconMap[skill.icon] ?? defaultIcon;
        const colors = colorClassMap[skill.color ?? ""] ?? defaultColor;
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
                      colors.text
                    )
              )}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full",
                    isSelected ? "bg-white/15" : colors.bg
                  )}
                >
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5",
                      isSelected ? "text-white" : colors.text
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
