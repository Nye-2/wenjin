"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { YamlEditor } from "../../components/YamlEditor";
import { Button } from "@/components/ui/button";
import {
  deleteAdminCapability,
  getAdminCapability,
  updateAdminCapability,
  validateAdminCapability,
} from "@/lib/api/admin-capabilities";

export default function CapabilityEditPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceType = searchParams.get("workspace_type") ?? "";

  const [yamlText, setYamlText] = useState("");
  const [originalYaml, setOriginalYaml] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceType) return;
    setIsLoading(true);
    getAdminCapability(id, workspaceType)
      .then((res) => {
        setYamlText(res.yaml);
        setOriginalYaml(res.yaml);
      })
      .finally(() => setIsLoading(false));
  }, [id, workspaceType]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (yamlText !== originalYaml) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [yamlText, originalYaml]);

  const handleValidate = useCallback(
    async (text: string) => {
      const res = await validateAdminCapability(text);
      setErrors(res.errors);
      return res.errors;
    },
    []
  );

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await updateAdminCapability(id, workspaceType, yamlText);
      setOriginalYaml(yamlText);
      router.push("/dashboard/admin/capabilities");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`确认删除 capability "${id}"？此操作不可恢复。`)) return;
    await deleteAdminCapability(id, workspaceType);
    router.push("/dashboard/admin/capabilities");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  const isDirty = yamlText !== originalYaml;
  const canSave = !isSaving && isDirty && errors.length === 0;

  return (
    <>
      <div className="route-card rounded-[1.75rem] p-6 mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/dashboard/admin/capabilities")}
          >
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)]">
              {id}{" "}
              <span className="text-sm text-[var(--text-muted)]">
                / {workspaceType}
              </span>
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/dashboard/admin/capabilities")}
            disabled={isSaving}
          >
            取消
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={isSaving}
          >
            删除
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!canSave}>
            {isSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            保存
          </Button>
        </div>
      </div>

      {saveError && (
        <div className="mb-4 rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          {saveError}
        </div>
      )}

      <YamlEditor
        initialValue={yamlText}
        onChange={setYamlText}
        onValidate={handleValidate}
        height="640px"
      />
    </>
  );
}
