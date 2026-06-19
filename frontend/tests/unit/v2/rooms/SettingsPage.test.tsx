import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { SettingsPage } from "@/app/(workbench)/workspaces/[id]/components/rooms/SettingsPage";

const MOCK_MEMORY_FACTS = [
  {
    id: "fact-1",
    content: "User prefers concise explanations",
    category: "preference",
    confidence: 0.92,
    created_at: "2026-01-15T10:00:00Z",
  },
  {
    id: "fact-2",
    content: "Project uses TypeScript and React",
    category: "fact",
    confidence: 0.99,
    created_at: "2026-01-14T08:00:00Z",
  },
];

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
    "/api/workspaces/ws-1/memory": MOCK_MEMORY_FACTS,
    "/api/workspaces/ws-1/decisions": MOCK_DECISIONS,
    "/api/workspaces/ws-1/settings": {
      name: "Test Workspace",
      auto_compact_threshold: 0.8,
      default_model: "claude-sonnet-4-6",
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

  it("renders with 3 tabs", () => {
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
    expect(screen.getByTestId("tab-memory")).toBeInTheDocument();
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

    // Default tab is Memory
    expect(screen.getByTestId("memory-viewer")).toBeInTheDocument();

    // Switch to Decisions
    fireEvent.click(screen.getByTestId("tab-decisions"));
    expect(screen.getByTestId("decisions-viewer")).toBeInTheDocument();

    // Switch to Settings (loads settings data async)
    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(await screen.findByTestId("settings-form")).toBeInTheDocument();
  });

  it("MemoryViewer fetches and displays facts", async () => {
    global.fetch = mockFetch();
    render(
      <SettingsPage
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("User prefers concise explanations");
    expect(screen.getByText("User prefers concise explanations")).toBeInTheDocument();
    expect(screen.getByText("Project uses TypeScript and React")).toBeInTheDocument();
    expect(screen.getByText("可信度 92%")).toBeInTheDocument();
    expect(screen.getAllByTestId("memory-item")).toHaveLength(2);
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

    const nameInput = screen.getByTestId("settings-name");
    fireEvent.change(nameInput, { target: { value: "My Workspace" } });

    const saveButton = screen.getByTestId("settings-save");
    fireEvent.click(saveButton);

    await screen.findByTestId("settings-saved");
    expect(screen.getByTestId("settings-saved")).toHaveTextContent(
      "设置已保存",
    );
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
