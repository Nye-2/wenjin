import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Archive, MoreHorizontal, Save, Trash2 } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";
import { OverflowMenu } from "@/components/ui/overflow-menu";

describe("ActionBar", () => {
  it("renders one primary action, secondary actions, and overflow without exposing hidden actions as peer buttons", () => {
    const { container } = render(
      <ActionBar
        primary={{ label: "全部接受", onClick: () => undefined }}
        secondary={[
          { label: "查看证据", onClick: () => undefined, icon: Archive },
        ]}
        overflow={[
          { label: "复制 ID", onClick: () => undefined, icon: MoreHorizontal },
          {
            label: "删除",
            onClick: () => undefined,
            icon: Trash2,
            tone: "danger",
          },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "全部接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看证据" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更多操作" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制 ID" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除" })).not.toBeInTheDocument();
    expect(
      Array.from(container.querySelectorAll("button")).map((button) =>
        button.textContent?.trim(),
      ),
    ).toEqual(["全部接受", "查看证据", ""]);
  });

  it("requires accessible labels for icon-only actions", () => {
    render(
      <ActionBar
        secondary={[
          {
            label: "保存",
            icon: Save,
            iconOnly: true,
            onClick: () => undefined,
          },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
  });
});

describe("OverflowMenu", () => {
  it("exposes menu disclosure state to assistive technology", () => {
    render(
      <OverflowMenu
        items={[
          {
            label: "删除项目",
            icon: Trash2,
            tone: "danger",
            onClick: () => undefined,
          },
        ]}
      />,
    );

    const trigger = screen.getByRole("button", { name: "更多操作" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu")).toHaveAttribute(
      "id",
      trigger.getAttribute("aria-controls"),
    );
  });

  it("dismisses the menu when the user clicks outside", () => {
    render(
      <div>
        <OverflowMenu
          items={[
            {
              label: "删除项目",
              icon: Trash2,
              tone: "danger",
              onClick: () => undefined,
            },
          ]}
        />
        <button type="button">外部按钮</button>
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menuitem", { name: "删除项目" })).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("button", { name: "外部按钮" }));

    expect(screen.queryByRole("menuitem", { name: "删除项目" })).not.toBeInTheDocument();
  });
});
