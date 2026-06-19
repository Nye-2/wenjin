import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommitActionBar } from "@/app/(workbench)/workspaces/[id]/components/result-preview/CommitActionBar";

describe("CommitActionBar", () => {
  it("keeps accept-all as the primary action and moves destructive deferral into overflow", () => {
    const onAcceptAll = vi.fn();
    const onAcceptSelected = vi.fn();
    const onDiscard = vi.fn();

    render(
      <CommitActionBar
        committed={false}
        committing={false}
        onAcceptAll={onAcceptAll}
        onAcceptSelected={onAcceptSelected}
        onDiscard={onDiscard}
        acceptAllLabel="全部接受"
        acceptSelectedLabel="保存已勾选"
        discardLabel="暂不保存"
      />,
    );

    expect(screen.getByRole("button", { name: "全部接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存已勾选" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "暂不保存" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "暂不保存" }));

    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  it("can make selected outputs the primary action when accept-all is unsafe", () => {
    const onAcceptAll = vi.fn();
    const onAcceptSelected = vi.fn();
    const onDiscard = vi.fn();

    render(
      <CommitActionBar
        committed={false}
        committing={false}
        allowAcceptAll={false}
        selectedCount={1}
        onAcceptAll={onAcceptAll}
        onAcceptSelected={onAcceptSelected}
        onDiscard={onDiscard}
        acceptAllLabel="全部接受"
        acceptSelectedLabel="保存已勾选"
      />,
    );

    expect(screen.queryByRole("button", { name: "全部接受" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存已勾选" }));

    expect(onAcceptAll).not.toHaveBeenCalled();
    expect(onAcceptSelected).toHaveBeenCalledTimes(1);
  });

  it("disables selected-output save when nothing is checked", () => {
    const onAcceptAll = vi.fn();
    const onAcceptSelected = vi.fn();
    const onDiscard = vi.fn();

    render(
      <CommitActionBar
        committed={false}
        committing={false}
        allowAcceptAll={false}
        selectedCount={0}
        onAcceptAll={onAcceptAll}
        onAcceptSelected={onAcceptSelected}
        onDiscard={onDiscard}
        acceptSelectedLabel="保存已勾选"
      />,
    );

    const button = screen.getByRole("button", { name: "保存已勾选" });
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(onAcceptSelected).not.toHaveBeenCalled();
  });
});
