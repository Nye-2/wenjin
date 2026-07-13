import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { SettingsPage } from "@/app/(workbench)/workspaces/[id]/components/rooms/SettingsPage";

const mockListModels = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listModels: mockListModels,
  };
});

const MOCK_DECISIONS = [
  {
    id: "dec-1",
    key: "architecture",
    value: "microservices",
    confidence: 0.85,
    rationale: "Better scalability for the team size",
    created_at: "2026-01-13T10:00:00Z",
  },
];

function mockFetch(overrides?: Record<string, unknown>) {
  const defaults: Record<string, unknown> = {
    "/api/workspaces/ws-1/decisions": MOCK_DECISIONS,
    "/api/workspaces/ws-1/settings": {
      name: "Test Workspace",
      auto_compact_threshold: 0.8,
      default_model: "gpt-5.6-sol",
      review_mode: "balanced_default",
    },
  };
  const responses = { ...defaults, ...overrides };

  return vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
    // Handle DELETE requests
    if (opts?.method === "DELETE") {
      return Promise.resolve({ ok: true });
    }
    // Handle POST/PUT to settings
    if (
      (opts?.method === "POST" || opts?.method === "PUT") &&
      url.includes("/settings")
    ) {
      return Promise.resolve({ ok: true });
    }
    // Handle GET by URL match
    for (const [path, data] of Object.entries(responses)) {
      if (url.includes(path)) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(data),
        });
      }
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    });
  });
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockListModels.mockResolvedValue({
      models: [
        {
          name: "gpt-5.6-sol",
          display_name: "GPT-5.6 Sol (Default)",
          provider: "sub2api",
          max_tokens: 128000,
          supports_thinking: false,
          supports_reasoning_effort: false,
          supports_vision: false,
          is_default: true,
        },
      ],
    });
  });

  it("renders nothing when closed", () => {
    global.fetch = vi.fn();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
  });

  it("renders without the hidden memory tab", () => {
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("settings-page")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tabs")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-memory")).not.toBeInTheDocument();
    expect(screen.getByTestId("tab-decisions")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-sandbox")).not.toBeInTheDocument();
    expect(screen.getByTestId("tab-settings")).toBeInTheDocument();
  });

  it("switches between tabs", async () => {
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    // Default tab is Decisions while workspace memory remains backend-only.
    expect(screen.getByTestId("decisions-viewer")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /记忆/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(await screen.findByTestId("settings-form")).toBeInTheDocument();
  });

  it("does not fetch or display memory facts from the settings panel", async () => {
    const fetchMock = mockFetch();
    global.fetch = fetchMock;
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/workspaces/ws-1/memory"),
      expect.anything(),
    );
    expect(screen.queryByTestId("memory-item")).not.toBeInTheDocument();
  });

  it("DecisionsViewer displays decisions", async () => {
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    // Switch to Decisions tab
    fireEvent.click(screen.getByTestId("tab-decisions"));

    await screen.findByText("architecture");
    expect(screen.getByText("architecture")).toBeInTheDocument();
    expect(screen.getByText("microservices")).toBeInTheDocument();
    expect(screen.getByText("Better scalability for the team size")).toBeInTheDocument();
    expect(screen.getByTestId("decision-item")).toBeInTheDocument();
  });

  it("SettingsForm saves settings", async () => {
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    // Switch to Settings tab
    fireEvent.click(screen.getByTestId("tab-settings"));

    await screen.findByTestId("settings-name");
    expect(screen.getByTestId("settings-default-model")).toHaveValue(
      "gpt-5.6-sol",
    );
    expect(screen.getByText("GPT-5.6 Sol (Default)")).toBeInTheDocument();
    expect(screen.getByTestId("review-mode-balanced_default")).toHaveAttribute(
      "aria-checked",
      "true",
    );

    const nameInput = screen.getByTestId("settings-name");
    fireEvent.change(nameInput, { target: { value: "My Workspace" } });
    fireEvent.click(screen.getByTestId("review-mode-review_all"));

    const saveButton = screen.getByTestId("settings-save");
    fireEvent.click(saveButton);

    await screen.findByTestId("settings-saved");
    expect(screen.getByTestId("settings-saved")).toHaveTextContent(
      "设置已保存",
    );
    const putCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url, init]) =>
        String(url).includes("/api/workspaces/ws-1/settings") &&
        (init as RequestInit | undefined)?.method === "PUT",
    );
    expect(putCall?.[1]).toMatchObject({
      body: JSON.stringify({
        name: "My Workspace",
        auto_compact_threshold: 0.8,
        default_model: "gpt-5.6-sol",
        review_mode: "review_all",
      }),
    });
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={onClose}
      />,
    );

    await screen.findByTestId("settings-close");
    fireEvent.click(screen.getByTestId("settings-close"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
