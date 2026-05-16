"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { YamlEditor } from "../../components/YamlEditor";
import { Button } from "@/components/ui/button";
import {
  createAdminCapability,
  validateAdminCapability,
} from "@/lib/api/admin-capabilities";

const TEMPLATE_YAML = `id: new_capability
workspace_type: thesis
display_name: 新能力
description: 简短描述
intent_description: 用户希望做什么
trigger_phrases: []
required_decisions: []
brief_schema:
  type: object
  properties: {}
  required: []
graph_template:
  phases:
    - name: phase1
      tasks:
        - name: t1
          subagent_type: react
          skill_id: null
          inputs: {}
          outputs: []
ui_meta:
  icon: search
  color: purple
  order: 0
  stages: []
  follow_up_prompt: null
notes: null
`;

export default function CapabilityCreatePage() {
  const router = useRouter();
  const [yamlText, setYamlText] = useState(TEMPLATE_YAML);
  const [errors, setErrors] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleValidate = useCallback(async (text: string) => {
    const res = await validateAdminCapability(text);
    setErrors(res.errors);
    return res.errors;
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await createAdminCapability(yamlText);
      router.push("/dashboard/admin/capabilities");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <div className="route-card rounded-[1.75rem] p-6 mb-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/dashboard/admin/capabilities")}
          >
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <h1 className="text-xl font-bold">新建 Capability</h1>
        </div>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={isSaving || errors.length > 0}
        >
          {isSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
          创建
        </Button>
      </div>

      {saveError && (
        <div className="mb-4 rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          {saveError}
        </div>
      )}

      <YamlEditor
        initialValue={TEMPLATE_YAML}
        onChange={setYamlText}
        onValidate={handleValidate}
        height="640px"
      />
    </>
  );
}
