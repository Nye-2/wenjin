import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { AutoCompactToast } from "@/app/(workbench)/workspaces/[id]/components/AutoCompactToast";

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AutoCompactToast", () => {
  it("renders nothing when not visible", () => {
    const { container } = render(
      <AutoCompactToast workspaceId="ws-1" visible={false} onDismiss={vi.fn()} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("shows compact prompt when visible", () => {
    render(<AutoCompactToast workspaceId="ws-1" visible={true} onDismiss={vi.fn()} />);
    expect(screen.getByText("上下文接近上限")).toBeInTheDocument();
    expect(screen.getByText("压缩")).toBeInTheDocument();
    expect(screen.getByText("稍后")).toBeInTheDocument();
  });

  it("calls compact endpoint on '压缩' click", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    render(<AutoCompactToast workspaceId="ws-1" visible={true} onDismiss={vi.fn()} />);
    fireEvent.click(screen.getByText("压缩"));
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/chat/compact",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows confirmation after successful compact", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    const onDismiss = vi.fn();
    render(
      <AutoCompactToast workspaceId="ws-1" visible={true} onDismiss={onDismiss} />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("压缩"));
      // Flush the microtask queue so the fetch promise resolves
      await vi.runAllTimersAsync();
    });

    expect(screen.getByText("上下文已压缩")).toBeInTheDocument();
    expect(onDismiss).toHaveBeenCalled();
  });

  it("calls onDismiss when '稍后' clicked", () => {
    const onDismiss = vi.fn();
    render(
      <AutoCompactToast workspaceId="ws-1" visible={true} onDismiss={onDismiss} />
    );
    fireEvent.click(screen.getByText("稍后"));
    expect(onDismiss).toHaveBeenCalled();
  });
});
