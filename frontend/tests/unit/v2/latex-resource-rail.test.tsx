import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LatexResourceRail } from "@/components/latex/latex-editor/LatexResourceRail";

const noopAsync = vi.fn().mockResolvedValue(undefined);

function renderRail() {
  return render(
    <LatexResourceRail
      tree={[
        {
          path: "main.tex",
          type: "file",
        },
      ]}
      selectedPath="main.tex"
      isProjectLoading={false}
      isDeletingProject={false}
      projectName="Research Draft"
      currentFolderLabel="根目录"
      onOpenFile={vi.fn()}
      onSelectPath={vi.fn()}
      onRenamePath={noopAsync}
      onDeletePath={noopAsync}
      onReorder={noopAsync}
      onCreateFile={noopAsync}
      onCreateFolder={noopAsync}
      onUploadFiles={noopAsync}
      onUploadDirectory={noopAsync}
      onUploadArchive={noopAsync}
      onDeleteProject={noopAsync}
    />,
  );
}

describe("LatexResourceRail", () => {
  it("keeps project-level save, compile, and delete actions out of the file rail", () => {
    renderRail();

    expect(screen.getByText("main.tex")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编译" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除项目" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "更多操作" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));

    expect(screen.getByRole("menuitem", { name: "删除项目" })).toBeInTheDocument();
  });

  it("uses a shared disclosure button for secondary file creation actions", () => {
    renderRail();

    const addFileButton = screen.getByRole("button", { name: "添加文件" });
    expect(addFileButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "新文件" })).not.toBeInTheDocument();

    fireEvent.click(addFileButton);

    expect(addFileButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "新文件" })).toBeInTheDocument();
    expect(screen.getByLabelText("新文件路径")).toBeInTheDocument();
    expect(screen.getByLabelText("新文件夹路径")).toBeInTheDocument();
  });
});
