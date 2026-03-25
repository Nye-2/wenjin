export interface ChatSkillSyncState {
  currentSkill: string | null;
  isSkillSelectionPending: boolean;
}

export function syncCurrentSkillWithThread(options: {
  currentSkill: string | null | undefined;
  nextThreadSkill: string | null | undefined;
  isSkillSelectionPending: boolean;
}): ChatSkillSyncState {
  const currentSkill = options.currentSkill ?? null;
  const nextThreadSkill = options.nextThreadSkill ?? null;

  if (!options.isSkillSelectionPending) {
    return {
      currentSkill: nextThreadSkill,
      isSkillSelectionPending: false,
    };
  }

  if (currentSkill === nextThreadSkill) {
    return {
      currentSkill,
      isSkillSelectionPending: false,
    };
  }

  return {
    currentSkill,
    isSkillSelectionPending: true,
  };
}
