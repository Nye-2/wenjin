import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mockResolveFeatureAction = vi.fn();

vi.mock("@/lib/api/workspace", () => ({
  resolveFeatureAction: (...args: unknown[]) => mockResolveFeatureAction(...args),
}));

import { resolveFeatureActionState } from "@/lib/workspace-feature-actions";

describe("workspace-feature-actions", () => {
  beforeEach(() => {
    mockResolveFeatureAction.mockReset();
  });

  it("delegates artifact follow-up context to the backend SSOT", async () => {
    mockResolveFeatureAction.mockResolvedValueOnce({
      source_artifact_id: "artifact-2",
      follow_up_prompt: "继续深化框架",
      route_params: {
        topic: "LLM planning",
        source_artifact_id: "artifact-2",
      },
      rerun_params: {
        topic: "LLM planning",
      },
      rerun_unavailable_reason: null,
    });

    const state = await resolveFeatureActionState({
      featureId: "framework_outline",
      feature: { id: "framework_outline" },
      workspace: {
        id: "workspace-1",
        name: "Workspace",
      } as never,
      artifacts: [
        {
          id: "artifact-2",
          title: "LLM Framework",
        } as never,
      ],
      orchestrationParams: {
        topic: "LLM planning",
        source_artifact_id: "artifact-2",
      },
    });

    expect(mockResolveFeatureAction).toHaveBeenCalledWith(
      "workspace-1",
      "framework_outline",
      {
        orchestration_params: {
          topic: "LLM planning",
          source_artifact_id: "artifact-2",
        },
        source_artifact_id: null,
      }
    );
    expect(state.sourceArtifact?.id).toBe("artifact-2");
    expect(state.routeParams.source_artifact_id).toBe("artifact-2");
    expect(state.rerunParams).toEqual({ topic: "LLM planning" });
  });

  it("does not keep frontend fallback task name fields", () => {
    const sourcePath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../lib/workspace-feature-actions.ts"
    );
    const source = readFileSync(sourcePath, "utf8");

    expect(source).not.toContain("fallbackTaskName");
    expect(source).not.toContain("未命名任务");
  });
});
