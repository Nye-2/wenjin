"use client";

import {
  forwardRef,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { LoaderCircle, Paperclip } from "lucide-react";
import { uploadThreadFiles } from "@/lib/api/threads";
import type { ThreadAttachment } from "@/lib/api/types";

interface FileAttachButtonProps {
  threadId: string | null;
  workspaceId: string;
  onAttached: (files: ThreadAttachment[]) => void;
  onError?: (message: string | null) => void;
  onUploadingChange?: (uploading: boolean) => void;
  disabled?: boolean;
}

export interface FileAttachButtonHandle {
  open: () => void;
}

export const FileAttachButton = forwardRef<
  FileAttachButtonHandle,
  FileAttachButtonProps
>(function FileAttachButton(
  {
    threadId,
    workspaceId,
    onAttached,
    onError,
    onUploadingChange,
    disabled,
  },
  ref,
) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const unavailable = disabled || uploading || !threadId;

  useImperativeHandle(
    ref,
    () => ({
      open: () => {
        if (!unavailable) {
          inputRef.current?.click();
        }
      },
    }),
    [unavailable],
  );

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length || !threadId) return;

    onError?.(null);
    setUploading(true);
    onUploadingChange?.(true);
    try {
      const result = await uploadThreadFiles({
        threadId,
        workspaceId,
        kind: "transient",
        files: Array.from(files),
      });
      if (result.files?.length) {
        onAttached(result.files);
      }
    } catch {
      onError?.("附件上传失败，请稍后重试。");
    } finally {
      setUploading(false);
      onUploadingChange?.(false);
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
        disabled={unavailable}
        aria-label={uploading ? "附件上传中" : "添加附件"}
        data-testid="chat-attachment-button"
        title={uploading ? "上传中..." : "添加附件"}
        style={{
          width: 32,
          height: 32,
          padding: 0,
          borderRadius: "var(--wjn-radius-md)",
          border: "none",
          background: "transparent",
          color: "var(--wjn-text-muted)",
          cursor: unavailable ? "not-allowed" : "pointer",
          opacity: unavailable ? 0.3 : 0.72,
          lineHeight: 1,
          flexShrink: 0,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {uploading ? (
          <LoaderCircle size={17} aria-hidden="true" className="animate-spin" />
        ) : (
          <Paperclip size={17} aria-hidden="true" />
        )}
      </button>
    </>
  );
});
