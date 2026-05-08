import { describe, expect, it } from "vitest";

import {
  buildWorkspaceThreadEntryPrompt,
  parseWorkspaceThreadEntrySeed,
  resolveWorkspaceThreadEntrySkill,
} from "@/lib/workspace-thread-entry";

describe("workspace-thread-entry", () => {
  it("returns null when feature param is missing", () => {
    const params = new URLSearchParams("skill=outline");
    expect(parseWorkspaceThreadEntrySeed(params)).toBeNull();
  });

  it("parses scalar and array params with type coercion", () => {
    const params = new URLSearchParams(
      "feature=thesis_plan&skill=outline&count=3&flag=true&tag=alpha&tag=beta&keep=007"
    );
    const seed = parseWorkspaceThreadEntrySeed(params);

    expect(seed).not.toBeNull();
    expect(seed?.featureId).toBe("thesis_plan");
    expect(seed?.skillId).toBe("outline");
    expect(seed?.params).toEqual({
      count: 3,
      flag: true,
      tag: ["alpha", "beta"],
      keep: "007",
    });
  });

  it("resolves skill from matching feature when seed skill is missing", () => {
    const selected = resolveWorkspaceThreadEntrySkill({
      seed: {
        featureId: "paper_outline",
        skillId: null,
        params: {},
      },
      skills: [
        {
          id: "outline-skill",
          featureId: "paper_outline",
          name: "Outline",
          description: "Build an outline",
          icon: "pen-tool",
          color: "blue",
          guidancePrompt: "prompt",
          followUpSkills: [],
        },
      ],
    });

    expect(selected).toBe("outline-skill");
  });

  it("builds onboarding and feature prompts", () => {
    const onboardingPrompt = buildWorkspaceThreadEntryPrompt({
      seed: {
        featureId: "__onboarding__",
        skillId: null,
        params: {},
      },
    });
    const featurePrompt = buildWorkspaceThreadEntryPrompt({
      seed: {
        featureId: "draft_proposal",
        skillId: null,
        params: {},
      },
      feature: { name: "开题撰写", description: "..." },
    });

    expect(onboardingPrompt).toContain("刚创建了这个工作区");
    expect(featurePrompt).toBe("请帮我开始「开题撰写」。");
  });

  // Lock down the URL → params contract that the chat page's entrySeed
  // flow uses to deliver context to lead_agent (via the seed prompt + skill).
  it("captures source_artifact_id, paper_title, paper_abstract into params", () => {
    const seed = parseWorkspaceThreadEntrySeed(
      new URLSearchParams({
        feature: "paper_analysis",
        source_artifact_id: "art-1",
        paper_title: "联邦学习+大模型",
        paper_abstract: "短摘要",
      }),
    );
    expect(seed?.params.source_artifact_id).toBe("art-1");
    expect(seed?.params.paper_title).toBe("联邦学习+大模型");
    expect(seed?.params.paper_abstract).toBe("短摘要");
  });

  it("captures entry=open|resume + onboarding=true via params", () => {
    const seed = parseWorkspaceThreadEntrySeed(
      new URLSearchParams({
        feature: "paper_analysis",
        entry: "open",
        onboarding: "true",
      }),
    );
    expect(seed?.params.entry).toBe("open");
    expect(seed?.params.onboarding).toBe(true);
  });

  it("never includes the reserved feature/skill keys inside params", () => {
    const seed = parseWorkspaceThreadEntrySeed(
      new URLSearchParams({
        feature: "x",
        skill: "y",
        other: "z",
      }),
    );
    expect(seed?.params).not.toHaveProperty("feature");
    expect(seed?.params).not.toHaveProperty("skill");
    expect(seed?.params.other).toBe("z");
  });
});
