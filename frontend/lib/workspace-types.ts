export const WORKSPACE_TYPES = [
  "sci",
  "thesis",
  "proposal",
  "software_copyright",
  "math_modeling",
  "patent",
] as const;

export type WorkspaceType = (typeof WORKSPACE_TYPES)[number];
