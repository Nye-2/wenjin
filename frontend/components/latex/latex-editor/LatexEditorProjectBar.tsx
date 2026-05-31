import {
  ArrowLeft,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { LatexCompileEngine } from "@/lib/api";

export function LatexEditorProjectBar({
  projectName,
  mainFile,
  activeFilePath,
  dirty,
  engine,
  isProjectLoading,
  isSaving,
  isCompiling,
  activeFileKind,
  isInspectorOpen,
  backLabel,
  onBack,
  onEngineChange,
  onSave,
  onCompile,
  onToggleInspector,
}: {
  projectName?: string | null;
  mainFile?: string | null;
  activeFilePath: string | null;
  dirty: boolean;
  engine: LatexCompileEngine;
  isProjectLoading: boolean;
  isSaving: boolean;
  isCompiling: boolean;
  activeFileKind: "text" | "blob" | null;
  isInspectorOpen: boolean;
  backLabel: string;
  onBack: () => void;
  onEngineChange: (engine: LatexCompileEngine) => void;
  onSave: () => void;
  onCompile: () => void;
  onToggleInspector: () => void;
}) {
  return (
    <div className="wjn-topbar flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-3 px-3 py-2 md:px-4">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={onBack}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {backLabel}
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-sm font-semibold text-[var(--wjn-text)]">
              {projectName || "加载项目中..."}
            </h1>
            <span className="rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white px-2 py-0.5 text-[11px] text-[var(--wjn-text-muted)]">
              {dirty ? "未保存" : "已保存"}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--wjn-text-muted)]">
            主文件 {mainFile || "main.tex"} · {activeFilePath || "未选择文件"}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <select
          value={engine}
          onChange={(event) => onEngineChange(event.target.value as LatexCompileEngine)}
          className="h-9 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white px-2 text-xs"
        >
          <option value="xelatex">XeLaTeX</option>
          <option value="pdflatex">PDFLaTeX</option>
        </select>
        <Button
          size="sm"
          variant="outline"
          onClick={onSave}
          disabled={isProjectLoading || isSaving || activeFileKind !== "text"}
        >
          {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          保存
        </Button>
        <Button
          size="sm"
          onClick={onCompile}
          disabled={isProjectLoading || isCompiling || isSaving}
        >
          {isCompiling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
          {isCompiling ? "编译中" : "编译"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onToggleInspector}
        >
          {isInspectorOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
