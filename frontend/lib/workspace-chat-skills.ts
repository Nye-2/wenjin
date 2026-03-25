import type { Workspace } from "@/lib/api";

export type WorkspaceType = Workspace["type"];

export interface WorkspaceChatSkillDefinition {
  id: string;
  name: string;
  description: string;
  icon: "search" | "list" | "file" | "book" | "pen" | "flask" | "lightbulb";
  colorClass: string;
  backgroundClass: string;
}

export const workspaceChatSkillMap: Record<
  WorkspaceType,
  readonly WorkspaceChatSkillDefinition[]
> = {
  thesis: [
    {
      id: "deep-research",
      name: "Deep Research",
      description: "Comprehensive literature analysis and idea generation",
      icon: "search",
      colorClass: "text-blue-500",
      backgroundClass: "bg-blue-500/10",
    },
    {
      id: "framework-designer",
      name: "Framework",
      description: "Generate thesis outline and chapter structure",
      icon: "list",
      colorClass: "text-purple-500",
      backgroundClass: "bg-purple-500/10",
    },
    {
      id: "fullpaper-writer",
      name: "Full Paper",
      description: "Draft the whole thesis from the current workspace context",
      icon: "file",
      colorClass: "text-emerald-500",
      backgroundClass: "bg-emerald-500/10",
    },
    {
      id: "literature-review",
      name: "Lit Review",
      description: "Generate a literature-review style opening research report",
      icon: "book",
      colorClass: "text-cyan-500",
      backgroundClass: "bg-cyan-500/10",
    },
  ],
  sci: [
    {
      id: "deep-research",
      name: "Deep Research",
      description: "Search literature and identify research gaps",
      icon: "search",
      colorClass: "text-blue-500",
      backgroundClass: "bg-blue-500/10",
    },
    {
      id: "framework-designer",
      name: "Framework",
      description: "Generate abstract, keywords, and paper outline",
      icon: "list",
      colorClass: "text-purple-500",
      backgroundClass: "bg-purple-500/10",
    },
    {
      id: "literature-review",
      name: "Lit Review",
      description: "Turn current context into a structured literature review",
      icon: "book",
      colorClass: "text-cyan-500",
      backgroundClass: "bg-cyan-500/10",
    },
    {
      id: "peer-reviewer",
      name: "Peer Review",
      description: "Review the latest draft and highlight revision priorities",
      icon: "flask",
      colorClass: "text-rose-500",
      backgroundClass: "bg-rose-500/10",
    },
    {
      id: "journal-recommender",
      name: "Journal",
      description: "Recommend candidate journals from the current manuscript state",
      icon: "lightbulb",
      colorClass: "text-amber-500",
      backgroundClass: "bg-amber-500/10",
    },
  ],
  proposal: [
    {
      id: "proposal-writer",
      name: "Proposal",
      description: "Generate a proposal outline from the current task context",
      icon: "pen",
      colorClass: "text-indigo-500",
      backgroundClass: "bg-indigo-500/10",
    },
    {
      id: "experiment-designer",
      name: "Experiment",
      description: "Design experiments, variables, and evaluation strategy",
      icon: "flask",
      colorClass: "text-violet-500",
      backgroundClass: "bg-violet-500/10",
    },
  ],
  software_copyright: [],
  patent: [],
} as const;

export function getWorkspaceChatSkills(
  workspaceType: WorkspaceType | null | undefined
): readonly WorkspaceChatSkillDefinition[] {
  return workspaceType ? workspaceChatSkillMap[workspaceType] ?? [] : [];
}

export function getWorkspaceChatSkillLabel(
  workspaceType: WorkspaceType | null | undefined,
  skillId: string | null | undefined
): string | null {
  if (!workspaceType || !skillId) {
    return null;
  }
  const skill = workspaceChatSkillMap[workspaceType]?.find(
    (entry) => entry.id === skillId
  );
  return skill?.name ?? null;
}

export function formatWorkspaceChatSkillLabel(
  workspaceType: WorkspaceType | null | undefined,
  skillId: string | null | undefined
): string | null {
  if (!skillId) {
    return null;
  }

  const canonicalLabel = getWorkspaceChatSkillLabel(workspaceType, skillId);
  if (canonicalLabel) {
    return canonicalLabel;
  }

  return skillId.trim().replace(/[-_]/g, " ");
}
