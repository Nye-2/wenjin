"use client";

import {
  File,
  FileText,
  FileCode,
  FileImage,
  FileJson,
  FileSpreadsheet,
  FileArchive,
  FileType,
  FileVideo,
  FileAudio,
  FilePieChart,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type FileTypeCategory =
  | "pdf"
  | "tex"
  | "code"
  | "image"
  | "json"
  | "csv"
  | "xlsx"
  | "doc"
  | "zip"
  | "audio"
  | "video"
  | "data"
  | "unknown";

const iconMap: Record<FileTypeCategory, React.ElementType> = {
  pdf: FileType,
  tex: FileCode,
  code: FileCode,
  image: FileImage,
  json: FileJson,
  csv: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  doc: FileText,
  zip: FileArchive,
  audio: FileAudio,
  video: FileVideo,
  data: FilePieChart,
  unknown: File,
};

const colorMap: Record<FileTypeCategory, string> = {
  pdf: "text-compute-red",
  tex: "text-compute-cyan",
  code: "text-compute-cyan",
  image: "text-compute-gold",
  json: "text-compute-gold",
  csv: "text-compute-green",
  xlsx: "text-compute-green",
  doc: "text-compute-text-secondary",
  zip: "text-compute-text-muted",
  audio: "text-compute-gold",
  video: "text-compute-red",
  data: "text-compute-cyan",
  unknown: "text-compute-text-muted",
};

export function getFileType(filename: string): FileTypeCategory {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  switch (ext) {
    case "pdf":
      return "pdf";
    case "tex":
    case "sty":
    case "cls":
      return "tex";
    case "js":
    case "ts":
    case "jsx":
    case "tsx":
    case "py":
    case "go":
    case "rs":
    case "c":
    case "cpp":
    case "h":
    case "java":
    case "rb":
    case "php":
    case "sh":
    case "bash":
      return "code";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "svg":
    case "webp":
    case "bmp":
      return "image";
    case "json":
      return "json";
    case "csv":
      return "csv";
    case "xlsx":
    case "xls":
      return "xlsx";
    case "doc":
    case "docx":
    case "md":
    case "txt":
    case "rtf":
      return "doc";
    case "zip":
    case "tar":
    case "gz":
    case "rar":
    case "7z":
      return "zip";
    case "mp3":
    case "wav":
    case "ogg":
    case "aac":
    case "flac":
      return "audio";
    case "mp4":
    case "avi":
    case "mov":
    case "wmv":
    case "mkv":
      return "video";
    default:
      return "unknown";
  }
}

interface FileIconProps {
  filename?: string;
  type?: FileTypeCategory;
  size?: number;
  className?: string;
}

export function FileIcon({
  filename,
  type,
  size = 16,
  className,
}: FileIconProps) {
  const fileType = type ?? (filename ? getFileType(filename) : "unknown");
  const Icon = iconMap[fileType];

  return (
    <Icon
      className={cn(colorMap[fileType], className)}
      style={{ width: size, height: size }}
    />
  );
}

interface FileExtensionBadgeProps {
  filename: string;
  className?: string;
}

export function FileExtensionBadge({
  filename,
  className,
}: FileExtensionBadgeProps) {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const fileType = getFileType(filename);

  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider",
        "bg-compute-surface text-compute-text-muted",
        colorMap[fileType],
        className
      )}
    >
      {ext}
    </span>
  );
}
