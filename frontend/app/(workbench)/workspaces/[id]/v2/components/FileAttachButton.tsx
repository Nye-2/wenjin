"use client";

import { useRef, useState } from "react";
import { uploadThreadFiles } from "@/lib/api/threads";

interface AttachedFile {
  name: string;
  path: string;
}

interface FileAttachButtonProps {
  threadId: string | null;
  workspaceId: string;
  onAttached: (files: AttachedFile[]) => void;
  disabled?: boolean;
}

export function FileAttachButton({ threadId, workspaceId, onAttached, disabled }: FileAttachButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length || !threadId) return;

    setUploading(true);
    try {
      const result = await uploadThreadFiles({
        threadId,
        workspaceId,
        kind: "transient",
        files: Array.from(files),
      });
      if (result.files?.length) {
        onAttached(
          result.files.map((f) => ({
            name: f.name ?? "file",
            path: f.path ?? "",
          })),
        );
      }
    } catch {
      // silent
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        onChange={handleChange}
        style={{ display: "none" }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading || !threadId}
        title={uploading ? "上传中..." : "添加附件"}
        style={{
          padding: "4px 8px",
          borderRadius: "var(--v2-radius-md)",
          border: "none",
          background: "transparent",
          color: "var(--v2-text-tertiary)",
          fontSize: 20,
          fontWeight: 300,
          cursor: disabled || uploading ? "not-allowed" : "pointer",
          fontFamily: "var(--v2-font-sans)",
          opacity: disabled || uploading || !threadId ? 0.3 : 0.7,
          lineHeight: 1,
          flexShrink: 0,
        }}
      >
        +
      </button>
    </>
  );
}
