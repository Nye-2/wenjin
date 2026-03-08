"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  BookOpen,
  FileText,
  FlaskConical,
  FileCheck,
  PenTool,
  ListOrdered,
  Award
} from "lucide-react";
import { cn } from "@/lib/utils";

const skills = [
  {
    id: "deep-research",
    name: "Deep Research",
    description: "Comprehensive literature analysis and idea generation",
    icon: Search,
    color: "text-blue-500",
  },
  {
    id: "framework-designer",
    name: "Framework Designer",
    description: "Generate paper abstract and outline",
    icon: ListOrdered,
    color: "text-purple-500",
  },
  {
    id: "fullpaper-writer",
    name: "Full Paper Writer",
    description: "End-to-end academic paper writing",
    icon: FileText,
    color: "text-emerald-500",
  },
  {
    id: "literature-review",
    name: "Literature Review",
    description: "Systematic literature review generation",
    icon: BookOpen,
    color: "text-cyan-500",
  },
  {
    id: "experiment-designer",
    name: "Experiment Designer",
    description: "Design scientific experiments",
    icon: FlaskConical,
    color: "text-orange-500",
  },
  {
    id: "peer-reviewer",
    name: "Peer Reviewer",
    description: "Review and critique papers",
    icon: FileCheck,
    color: "text-red-500",
  },
  {
    id: "proposal-writer",
    name: "Proposal Writer",
    description: "Write research proposals",
    icon: PenTool,
    color: "text-indigo-500",
  },
  {
    id: "journal-recommender",
    name: "Journal Recommender",
    description: "Recommend suitable journals",
    icon: Award,
    color: "text-amber-500",
  },
];

interface SkillSelectorProps {
  onSelect: (skillId: string) => void;
  selectedSkill?: string;
}

export function SkillSelector({ onSelect, selectedSkill }: SkillSelectorProps) {
  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null);

  return (
    <div className="flex flex-wrap gap-2">
      {skills.map((skill) => {
        const Icon = skill.icon;
        const isSelected = selectedSkill === skill.id;
        const isHovered = hoveredSkill === skill.id;

        return (
          <motion.button
            key={skill.id}
            onClick={() => onSelect(skill.id)}
            onMouseEnter={() => setHoveredSkill(skill.id)}
            onMouseLeave={() => setHoveredSkill(null)}
            className={cn(
              "relative px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200",
              "border border-border/50",
              isSelected
                ? "bg-academic-primary text-white border-academic-primary"
                : "bg-white/50 hover:bg-white/80"
            )}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <span className="flex items-center gap-2">
              <Icon className={cn("w-4 h-4", isSelected ? "text-white" : skill.color)} />
              {skill.name}
            </span>

            <AnimatePresence>
              {isHovered && !isSelected && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute left-0 right-0 top-full mt-2 p-3 rounded-lg bg-popover text-xs text-popover-foreground shadow-lg z-50"
                >
                  {skill.description}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        );
      })}
    </div>
  );
}
