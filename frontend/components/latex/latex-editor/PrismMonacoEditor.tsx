import {
  forwardRef,
  useImperativeHandle,
  useRef,
} from "react";
import Editor, { loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

import { languageForPath } from "./fileKinds";

const monacoGlobal = globalThis as typeof globalThis & {
  MonacoEnvironment?: {
    getWorker?: (workerId: string, label: string) => Worker;
  };
};

if (typeof window !== "undefined" && !monacoGlobal.MonacoEnvironment) {
  monacoGlobal.MonacoEnvironment = {
    getWorker: () =>
      new Worker(
        new URL(
          "monaco-editor/esm/vs/editor/editor.worker.js",
          import.meta.url,
        ),
        { type: "module" },
      ),
  };
}

loader.config({ monaco });

export interface PrismTextEditorHandle {
  focus: () => void;
  setSelectionRange: (start: number, end: number) => void;
}

interface PrismMonacoEditorProps {
  path: string | null;
  value: string;
  readOnly: boolean;
  onChange: (value: string) => void;
  onSelect: (range: [number, number]) => void;
}

export const PrismMonacoEditor = forwardRef<PrismTextEditorHandle, PrismMonacoEditorProps>(
  function PrismMonacoEditor(
    {
      path,
      value,
      readOnly,
      onChange,
      onSelect,
    },
    ref,
  ) {
    const monacoEditorRef = useRef<Parameters<OnMount>[0] | null>(null);
    const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);

    useImperativeHandle(ref, () => ({
      focus() {
        monacoEditorRef.current?.focus();
      },
      setSelectionRange(start: number, end: number) {
        const editor = monacoEditorRef.current;
        const monaco = monacoRef.current;
        const model = editor?.getModel();
        if (!editor || !monaco || !model) {
          return;
        }
        const safeStart = Math.max(0, Math.min(start, model.getValueLength()));
        const safeEnd = Math.max(safeStart, Math.min(end, model.getValueLength()));
        const startPosition = model.getPositionAt(safeStart);
        const endPosition = model.getPositionAt(safeEnd);
        const selection = new monaco.Selection(
          startPosition.lineNumber,
          startPosition.column,
          endPosition.lineNumber,
          endPosition.column,
        );
        editor.setSelection(selection);
        editor.revealRangeInCenter(selection, 0);
        editor.focus();
      },
    }), []);

    const handleMount: OnMount = (editor, monaco) => {
      monacoEditorRef.current = editor;
      monacoRef.current = monaco;
      editor.onDidChangeCursorSelection((event) => {
        const model = editor.getModel();
        if (!model) {
          return;
        }
        const start = model.getOffsetAt(event.selection.getStartPosition());
        const end = model.getOffsetAt(event.selection.getEndPosition());
        onSelect([Math.min(start, end), Math.max(start, end)]);
      });
    };

    return (
      <Editor
        key={path || "prism-editor"}
        height="100%"
        value={value}
        language={languageForPath(path)}
        onMount={handleMount}
        onChange={(nextValue) => onChange(nextValue ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          lineHeight: 22,
          wordWrap: "on",
          scrollBeyondLastLine: false,
          folding: true,
          lineNumbersMinChars: 3,
          renderLineHighlight: "line",
          automaticLayout: true,
          padding: { top: 14, bottom: 14 },
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          smoothScrolling: true,
          tabSize: 2,
        }}
        theme="vs"
      />
    );
  },
);
