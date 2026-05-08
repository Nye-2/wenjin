"use client";

import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import type { TextBlock as TextBlockType } from "@/lib/api/blocks";

export function TextBlock({ block }: { block: TextBlockType }) {
  return <MarkdownRenderer content={block.content} />;
}
