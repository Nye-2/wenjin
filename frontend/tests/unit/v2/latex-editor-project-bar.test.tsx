import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LatexEditorProjectBar } from "@/components/latex/latex-editor/LatexEditorProjectBar";

function renderProjectBar() {
  return render(
    <LatexEditorProjectBar
      projectName="Research Draft"
      mainFile="main.tex"
      activeFilePath="main.tex"
      dirty={false}
      engine="xelatex"
      isProjectLoading={false}
      isSaving={false}
      isCompiling={false}
      activeFileKind="text"
      backLabel="Workbench"
      onBack={vi.fn()}
      onEngineChange={vi.fn()}
      onSave={vi.fn()}
      onCompile={vi.fn()}
    />,
  );
}

describe("LatexEditorProjectBar", () => {
  it("keeps project actions focused and leaves AI entry to the floating assist", () => {
    renderProjectBar();

    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "编译" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开 改稿助手" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "关闭 改稿助手" })).not.toBeInTheDocument();
  });
});
