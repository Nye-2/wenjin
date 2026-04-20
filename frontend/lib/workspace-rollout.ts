import type { Workspace } from "@/lib/api";

const THREAD_COCKPIT_DEFAULT_TYPES = new Set([
  "thesis",
  "sci",
  "proposal",
  "software_copyright",
  "patent",
]);

function readRollout(workspace: Workspace | null | undefined): Record<string, unknown> {
  const rollout = workspace?.config?.rollout;
  return rollout && typeof rollout === "object" ? rollout as Record<string, unknown> : {};
}

export function isWorkspaceThreadCockpitEnabled(
  workspace: Workspace | null | undefined
): boolean {
  if (!workspace) {
    return false;
  }
  const rollout = readRollout(workspace);
  if (typeof rollout.thread_cockpit_enabled === "boolean") {
    return rollout.thread_cockpit_enabled;
  }
  return THREAD_COCKPIT_DEFAULT_TYPES.has(workspace.type);
}
