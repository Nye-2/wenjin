import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  authorizedFetchMock,
  getWorkspaceSettingsMock,
  listModelsMock,
  updateWorkspaceSettingsMock,
  uploadThreadFilesMock,
} = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
  getWorkspaceSettingsMock: vi.fn(),
  listModelsMock: vi.fn(),
  updateWorkspaceSettingsMock: vi.fn(),
  uploadThreadFilesMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return {
    ...actual,
    getWorkspaceSettings: getWorkspaceSettingsMock,
    listModels: listModelsMock,
    updateWorkspaceSettings: updateWorkspaceSettingsMock,
  };
});

vi.mock("@/lib/api/threads", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/threads")>(
    "@/lib/api/threads",
  );
  return { ...actual, uploadThreadFiles: uploadThreadFilesMock };
});

import { ChatPanel } from "@/app/(workbench)/workspaces/[id]/components/ChatPanel";
import { useChatStoreV2 } from "@/stores/chat-store";

describe("ChatPanel composer", () => {
  beforeEach(() => {
    authorizedFetchMock.mockReset();
    getWorkspaceSettingsMock.mockReset();
    listModelsMock.mockReset();
    updateWorkspaceSettingsMock.mockReset();
    uploadThreadFilesMock.mockReset();
    useChatStoreV2.getState().reset();
    authorizedFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    listModelsMock.mockResolvedValue({
      models: [
        {
          name: "gpt-5.6-luna",
          display_name: "GPT-5.6 Luna",
          provider: "OpenAI",
          max_tokens: 128000,
          generation_api: "chat_completions",
          capability_profile_version: "probe-v1",
          capability_profile: {
            strict_tool_calls: true,
            streaming: true,
            reasoning_efforts: ["low", "medium", "high", "xhigh"],
            vision: true,
            native_web_search: true,
          },
          is_default: true,
        },
      ],
    });
    getWorkspaceSettingsMock.mockResolvedValue({
      workspace_id: "workspace-1",
      default_model: "gpt-5.6-luna",
      reasoning_effort: "xhigh",
      auto_compact_threshold: 0.8,
      review_mode: "balanced_default",
      settings_json: { review_mode: "balanced_default" },
      metadata_json: {},
    });
    updateWorkspaceSettingsMock.mockResolvedValue({});
  });

  it("hydrates and persists the workspace model preference", async () => {
    getWorkspaceSettingsMock.mockResolvedValueOnce({
      workspace_id: "workspace-1",
      default_model: "gpt-5.6-luna",
      reasoning_effort: "low",
      auto_compact_threshold: 0.8,
      review_mode: "balanced_default",
      settings_json: { review_mode: "balanced_default" },
      metadata_json: {},
    });

    render(<ChatPanel workspaceId="workspace-1" />);

    const selector = await screen.findByTestId("chat-model-selector");
    await waitFor(() => expect(selector).toHaveTextContent("低"));
    fireEvent.click(selector);
    fireEvent.click(screen.getByTestId("chat-reasoning-option-high"));

    await waitFor(() =>
      expect(updateWorkspaceSettingsMock).toHaveBeenCalledWith(
        "workspace-1",
        { reasoning_effort: "high" },
      ),
    );
    expect(selector).toHaveTextContent("高");
  });

  it("keeps send disabled until an in-flight attachment is available", async () => {
    let resolveUpload: ((value: unknown) => void) | undefined;
    uploadThreadFilesMock.mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve;
      }),
    );
    const { container } = render(<ChatPanel workspaceId="workspace-1" />);
    const composer = await screen.findByTestId("chat-composer-input");
    const attachmentButton = await screen.findByTestId(
      "chat-attachment-button",
    );
    await waitFor(() => expect(attachmentButton).toBeEnabled());
    fireEvent.change(composer, { target: { value: "分析这份赛题" } });

    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    expect(input).not.toBeNull();
    fireEvent.change(input!, {
      target: {
        files: [new File(["problem"], "problem.pdf", { type: "application/pdf" })],
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("chat-send")).toBeDisabled();
      expect(composer).toHaveAttribute("placeholder", "附件上传中...");
    });
    resolveUpload?.({
      files: [
        {
          name: "problem.pdf",
          path: "uploads/problem.pdf",
          kind: "transient",
          url: "/api/threads/thread-1/artifacts/uploads/problem.pdf",
          content_type: "application/pdf",
          size_bytes: 7,
          reference_id: "mission-input:" + "a".repeat(64),
          artifact_id: null,
          metadata: {},
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByTestId("chat-send")).toBeEnabled();
      expect(screen.getByText("problem.pdf")).toBeInTheDocument();
    });
  });
});
