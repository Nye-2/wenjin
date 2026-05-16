"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  { ssr: false }
);

interface Props {
  initialValue: string;
  onChange: (value: string) => void;
  onValidate: (yamlText: string) => Promise<string[]>;
  height?: string;
}

export function YamlEditor({
  initialValue,
  onChange,
  onValidate,
  height = "600px",
}: Props) {
  const [value, setValue] = useState(initialValue);
  const [errors, setErrors] = useState<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const errs = await onValidate(value);
      setErrors(errs);
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value, onValidate]);

  const handleChange = (v: string | undefined) => {
    const next = v ?? "";
    setValue(next);
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-[var(--border-default)] overflow-hidden">
        <MonacoEditor
          height={height}
          defaultLanguage="yaml"
          value={value}
          onChange={handleChange}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            wordWrap: "on",
            tabSize: 2,
            scrollBeyondLastLine: false,
          }}
          theme="vs-dark"
        />
      </div>
      {errors.length > 0 ? (
        <div className="rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 space-y-1">
          {errors.map((err, i) => (
            <div key={i} className="text-xs text-rose-700 font-mono">
              {err}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-emerald-600">
          Syntax OK / schema validated
        </div>
      )}
    </div>
  );
}
