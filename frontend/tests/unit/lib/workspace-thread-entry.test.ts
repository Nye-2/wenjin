import { describe, expect, it } from "vitest";

import {
  buildWorkspaceThreadEntryMetadata,
  buildWorkspaceThreadEntryPrompt,
  parseWorkspaceThreadEntrySeed,
  resolveWorkspaceThreadEntrySkill,
} from "@/lib/workspace-thread-entry";

describe("workspace-thread-entry", () => {
  it("returns null when search params are unavailable", () => {
    expect(parseWorkspaceThreadEntrySeed(null)).toBeNull();
  });

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

  it("returns the URL-encoded skill id when present, null otherwise", () => {
    expect(
      resolveWorkspaceThreadEntrySkill({
        seed: {
          featureId: "paper_outline",
          skillId: "outline-skill",
          params: {},
        },
      }),
    ).toBe("outline-skill");

    expect(
      resolveWorkspaceThreadEntrySkill({
        seed: {
          featureId: "paper_outline",
          skillId: null,
          params: {},
        },
      }),
    ).toBeNull();

    expect(resolveWorkspaceThreadEntrySkill({ seed: null })).toBeNull();
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

  it("includes seeded paper context in the launch prompt", () => {
    const featurePrompt = buildWorkspaceThreadEntryPrompt({
      seed: {
        featureId: "paper_analysis",
        skillId: "paper-analyst",
        params: {
          paper_title: "联邦学习+大模型",
          paper_abstract: "研究联邦场景下的大模型协同训练。",
        },
      },
      feature: { name: "论文分析", description: "..." },
    });

    expect(featurePrompt).toContain("请帮我开始「论文分析」");
    expect(featurePrompt).toContain("联邦学习+大模型");
    expect(featurePrompt).toContain("研究联邦场景下的大模型协同训练");
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

  it("surfaces execution_id into orchestration metadata for resume entries", () => {
    const metadata = buildWorkspaceThreadEntryMetadata({
      seed: {
        featureId: "paper_analysis",
        skillId: "paper-analyst",
        params: {
          entry: "resume",
          execution_id: "exec-123",
          paper_title: "联邦学习+大模型",
        },
      },
    });

    expect(metadata).toEqual({
      entry_seed: {
        feature_id: "paper_analysis",
        skill_id: "paper-analyst",
        params: {
          entry: "resume",
          execution_id: "exec-123",
          paper_title: "联邦学习+大模型",
        },
      },
      orchestration: {
        feature_id: "paper_analysis",
        source: "workspace_entry",
        entry: "resume",
        execution_id: "exec-123",
        params: {
          entry: "resume",
          execution_id: "exec-123",
          paper_title: "联邦学习+大模型",
        },
      },
    });
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
