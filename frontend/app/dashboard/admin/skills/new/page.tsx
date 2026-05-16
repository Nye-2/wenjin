"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { YamlEditor } from "../../components/YamlEditor";
import { Button } from "@/components/ui/button";
import {
  createAdminSkill,
  validateAdminSkill,
} from "@/lib/api/admin-skills";

const TEMPLATE_YAML = `id: new-skill
display_name: 新技能
description: 简短描述
subagent_type: react
prompt: |
  你是一个助手。
allowed_tools: []
resources: []
config: {}
`;

export default function SkillCreatePage() {
  const router = useRouter();
  const [yamlText, setYamlText] = useState(TEMPLATE_YAML);
  const [errors, setErrors] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleValidate = useCallback(async (text: string) => {
    const res = await validateAdminSkill(text);
    setErrors(res.errors);
    return res.errors;
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await createAdminSkill(yamlText);
      router.push("/dashboard/admin/skills");
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
            onClick={() => router.push("/dashboard/admin/skills")}
          >
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <h1 className="text-xl font-bold">新建 Skill</h1>
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
