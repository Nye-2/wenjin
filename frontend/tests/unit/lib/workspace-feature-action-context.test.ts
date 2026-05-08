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

  it("keeps artifact follow-up seeds in the chat route", async () => {
    mockResolveFeatureActionState.mockResolvedValueOnce({
      routeParams: {
        topic: "proposal topic",
        source_artifact_id: "artifact-2",
        context_artifact_ids: ["artifact-2"],
      },
      followUpPrompt: "",
      rerunParams: {
        topic: "proposal topic",
        context_artifact_ids: ["artifact-2"],
      },
      rerunUnavailableReason: null,
    });

    const context = await resolveWorkspaceFeatureActionContext({
      workspaceId: "workspace-1",
      featureId: "framework_outline",
      feature: {
        id: "framework_outline",
        defaultSkillId: "framework-designer",
      },
      workspace: null,
      artifacts: [],
    });

    expect(context.route).toBe(
      "/workspaces/workspace-1/chat?feature=framework_outline&skill=framework-designer&topic=proposal+topic&source_artifact_id=artifact-2&context_artifact_ids=artifact-2"
    );
    expect(context.routeParams).toEqual({
      topic: "proposal topic",
      source_artifact_id: "artifact-2",
      context_artifact_ids: ["artifact-2"],
    });
  });
});
