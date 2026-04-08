"use client";

import { useParams } from "next/navigation";

import { LatexEditorShell } from "@/components/latex/LatexEditorShell";

export default function LatexProjectPage() {
  const params = useParams();
  const projectId = String(params.projectId || "");

  return <LatexEditorShell projectId={projectId} />;
}
