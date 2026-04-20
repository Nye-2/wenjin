import { describe, expect, it } from "vitest";

import {
  createCommittedSkillState,
  createPendingSkillSelection,
  resolveActiveSkill,
  syncCurrentSkillWithThread,
} from "@/lib/thread-skill-state";

describe("thread-skill-state", () => {
  it("commits to thread skill when no pending selection", () => {
    const result = syncCurrentSkillWithThread({
      currentSkill: "outline",
      nextThreadSkill: "research",
      isSkillSelectionPending: false,
    });

    expect(result).toEqual({
      currentSkill: null,
      threadSkill: "research",
      activeSkill: "research",
      isSkillSelectionPending: false,
    });
  });

  it("clears pending state when thread catches up to selected skill", () => {
    const result = syncCurrentSkillWithThread({
      currentSkill: "outline",
      nextThreadSkill: "outline",
      isSkillSelectionPending: true,
    });

    expect(result.isSkillSelectionPending).toBe(false);
    expect(result.activeSkill).toBe("outline");
    expect(result.currentSkill).toBeNull();
  });

  it("keeps pending selected skill while thread is still behind", () => {
    const result = syncCurrentSkillWithThread({
      currentSkill: "outline",
      nextThreadSkill: "research",
      isSkillSelectionPending: true,
    });

    expect(result).toEqual({
      currentSkill: "outline",
      threadSkill: "research",
      activeSkill: "outline",
      isSkillSelectionPending: true,
    });
  });

  it("supports pending/committed helpers", () => {
    const pending = createPendingSkillSelection({
      skill: "draft",
      threadSkill: "research",
    });
    const committed = createCommittedSkillState("draft");

    expect(resolveActiveSkill(pending)).toBe("draft");
    expect(resolveActiveSkill(committed)).toBe("draft");
  });
});
