export interface ThreadSkillSyncState {
  currentSkill: string | null;
  threadSkill: string | null;
  activeSkill: string | null;
  isSkillSelectionPending: boolean;
}

function normalizeSkill(skill: string | null | undefined): string | null {
  return skill ?? null;
}

export function syncCurrentSkillWithThread(options: {
  currentSkill: string | null | undefined;
  nextThreadSkill: string | null | undefined;
  isSkillSelectionPending: boolean;
}): ThreadSkillSyncState {
  const currentSkill = normalizeSkill(options.currentSkill);
  const nextThreadSkill = normalizeSkill(options.nextThreadSkill);

  if (!options.isSkillSelectionPending) {
    return {
      currentSkill: null,
      threadSkill: nextThreadSkill,
      activeSkill: nextThreadSkill,
      isSkillSelectionPending: false,
    };
  }

  if (currentSkill === nextThreadSkill) {
    return {
      currentSkill: null,
      threadSkill: nextThreadSkill,
      activeSkill: nextThreadSkill,
      isSkillSelectionPending: false,
    };
  }

  return {
    currentSkill,
    threadSkill: nextThreadSkill,
    activeSkill: currentSkill,
    isSkillSelectionPending: true,
  };
}

export function resolveActiveSkill(options: {
  currentSkill: string | null | undefined;
  threadSkill: string | null | undefined;
  isSkillSelectionPending: boolean;
}): string | null {
  if (options.isSkillSelectionPending) {
    return normalizeSkill(options.currentSkill);
  }
  return normalizeSkill(options.threadSkill);
}

export function createPendingSkillSelection(options: {
  skill: string | null | undefined;
  threadSkill?: string | null | undefined;
}): ThreadSkillSyncState {
  const skill = normalizeSkill(options.skill);
  const threadSkill = normalizeSkill(options.threadSkill);
  return {
    currentSkill: skill,
    threadSkill,
    activeSkill: skill,
    isSkillSelectionPending: true,
  };
}

export function createCommittedSkillState(
  threadSkill: string | null | undefined = null
): ThreadSkillSyncState {
  const normalizedThreadSkill = normalizeSkill(threadSkill);
  return {
    currentSkill: null,
    threadSkill: normalizedThreadSkill,
    activeSkill: normalizedThreadSkill,
    isSkillSelectionPending: false,
  };
}
