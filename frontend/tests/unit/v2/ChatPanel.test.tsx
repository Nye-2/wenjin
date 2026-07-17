import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
import { useMissionUiStore } from "@/stores/mission-ui-store";

const originalSendMessage = useChatStoreV2.getState().sendMessage;
const originalStopSending = useChatStoreV2.getState().stopSending;

describe("ChatPanel composer", () => {
  beforeEach(() => {
    authorizedFetchMock.mockReset();
    getWorkspaceSettingsMock.mockReset();
    listModelsMock.mockReset();
    updateWorkspaceSettingsMock.mockReset();
    uploadThreadFilesMock.mockReset();
    useChatStoreV2.getState().reset();
    useMissionUiStore.getState().clearWorkspaceFocus();
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

  afterEach(() => {
    useChatStoreV2.setState({
      sendMessage: originalSendMessage,
      stopSending: originalStopSending,
    });
  });

  it("shows a stop control that cancels the active server run", async () => {
    const stopSending = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ isSending: true, stopSending });

    render(<ChatPanel workspaceId="workspace-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "停止生成" }));
    expect(stopSending).toHaveBeenCalledTimes(1);
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

  it("does not hard-route chat when the user only browses a historical Mission", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ status: "completed" });
    useChatStoreV2.setState({ sendMessage });
    useMissionUiStore.getState().focusMission("mission-history", "artifacts");
    render(<ChatPanel workspaceId="workspace-1" />);
    const composer = await screen.findByTestId("chat-composer-input");

    fireEvent.change(composer, { target: { value: "开始一个新的分析" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage.mock.calls[0][3]?.metadata?.focused_mission_id).toBeUndefined();
  });

  it("sends and consumes an explicit Mission continuation target", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ status: "completed" });
    useChatStoreV2.setState({ sendMessage });
    useMissionUiStore.getState().setContinuationMission("mission-explicit");
    render(<ChatPanel workspaceId="workspace-1" />);
    const composer = await screen.findByTestId("chat-composer-input");

    fireEvent.change(composer, { target: { value: "补充这项任务的材料" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage.mock.calls[0][3]).toMatchObject({
      metadata: { focused_mission_id: "mission-explicit" },
    });
    await waitFor(() => {
      expect(useMissionUiStore.getState().continuationMissionId).toBeNull();
    });
  });

  it("retains the Mission continuation target when a result-card action is cancelled", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ status: "cancelled" });
    useChatStoreV2.setState({ sendMessage });
    useMissionUiStore.getState().setContinuationMission("mission-explicit");
    render(<ChatPanel workspaceId="workspace-1" />);
    await screen.findByTestId("chat-composer-input");

    act(() => {
      useChatStoreV2.setState({
        messagesByWorkspace: {
          "workspace-1": [
            {
              id: "assistant-result",
              role: "assistant",
              createdAt: "2026-07-16T00:00:00Z",
              blocks: [
                {
                  kind: "result_card",
                  run_id: "mission-explicit",
                  title: "阶段结果",
                  tldr: "已有结果。",
                  findings: [],
                  links: [],
                  feedback: {
                    question: "继续吗？",
                    pills: [{ kind: "primary", label: "继续", intent: "继续完善" }],
                    allow_free_input: true,
                  },
                  stats: { duration_ms: 1, subagents: 0, tokens: 1 },
                },
              ],
            },
          ],
        },
      });
    });

    fireEvent.click(await screen.findByRole("button", { name: "继续" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage.mock.calls[0][3]).toMatchObject({
      metadata: { focused_mission_id: "mission-explicit" },
    });
    expect(useMissionUiStore.getState().continuationMissionId).toBe("mission-explicit");
  });
});
