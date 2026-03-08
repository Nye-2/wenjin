"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  BookOpen,
  FileText,
  ListOrdered,
  PenTool,
} from "lucide-react";
import { cn } from "@/lib/utils";

const skills = [
  {
    id: "deep-research",
    name: "Deep Research",
    description: "Comprehensive literature analysis and idea generation",
    icon: Search,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  {
    id: "framework-designer",
    name: "Framework",
    description: "Generate paper abstract and outline",
    icon: ListOrdered,
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
  },
  {
    id: "fullpaper-writer",
    name: "Full Paper",
    description: "End-to-end academic paper writing",
    icon: FileText,
    color: "text-emerald-500",
    bgColor: "bg-emerald-500/10",
  },
  {
    id: "literature-review",
    name: "Lit Review",
    description: "Systematic literature review generation",
    icon: BookOpen,
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
  },
  {
    id: "proposal-writer",
    name: "Proposal",
    description: "Write research proposals",
    icon: PenTool,
    color: "text-indigo-500",
    bgColor: "bg-indigo-500/10",
  },
];

interface SkillSelectorProps {
  selectedSkill?: string | null;
  onSelect: (skillId: string | null) => void;
}

export function SkillSelector({ selectedSkill, onSelect }: SkillSelectorProps) {
  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null);

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
        const Icon = skill.icon;
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
                "border border-white/20",
                isSelected
                  ? "bg-academic-primary text-white border-academic-primary"
                  : cn(
                      "bg-white/50 dark:bg-white/5",
                      "hover:bg-white/80 dark:hover:bg-white/10",
                      skill.color
                    )
              )}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <span className="flex items-center gap-1.5">
                <Icon
                  className={cn(
                    "w-3.5 h-3.5",
                    isSelected ? "text-white" : skill.color
                  )}
                />
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
                    "bg-slate-900 dark:bg-slate-800 text-white text-xs",
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
