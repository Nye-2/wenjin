import { beforeEach, describe, expect, it, vi } from "vitest";

const mockResolveFeatureActionState = vi.fn();

vi.mock("@/lib/workspace-feature-actions", () => ({
  resolveFeatureActionState: (...args: unknown[]) =>
    mockResolveFeatureActionState(...args),
}));

import { resolveWorkspaceFeatureActionContext } from "@/lib/workspace-feature-action-context";

describe("workspace-feature-action-context", () => {
  beforeEach(() => {
    mockResolveFeatureActionState.mockReset();
    mockResolveFeatureActionState.mockResolvedValue({
      routeParams: { skill: "explicit-skill", topic: "proposal topic" },
      followUpPrompt: "",
      rerunParams: null,
      rerunUnavailableReason: null,
    });
  });

  it("preserves explicit route skill over the feature default skill", async () => {
    const context = await resolveWorkspaceFeatureActionContext({
      workspaceId: "workspace-1",
      featureId: "feature-1",
      feature: {
        id: "feature-1",
        defaultSkillId: "default-skill",
      },
      workspace: null,
      artifacts: [],
    });

    expect(context.route).toBe(
      "/workspaces/workspace-1/chat?feature=feature-1&skill=explicit-skill&topic=proposal+topic"
    );
  });
});
