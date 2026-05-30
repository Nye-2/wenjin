"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  createAdminModel,
  updateAdminModel,
  type AdminModelCreatePayload,
  type AdminModelUpdatePayload,
} from "@/lib/api/admin-models";
import type { AdminModelCatalogItem } from "@/lib/api/types";

type Props = {
  open: boolean;
  model: AdminModelCatalogItem | null;
  onClose: (refresh: boolean) => void;
};

const INITIAL_FORM = {
  model_id: "",
  display_name: "",
  provider_name: "Custom",
  category: "llm",
  model_name: "",
  base_url: "",
  api_key: "",
  pricing_policy_id: "",
  max_tokens: "4096",
  temperature: "0.7",
  supports_streaming: true,
  supports_tools: false,
  supports_json_mode: true,
  supports_json_schema: false,
  supports_vision: false,
  supports_reasoning_effort: false,
  is_default: false,
};

type ModelFormState = typeof INITIAL_FORM;

export function ModelDialog({ open, model, onClose }: Props) {
  const isEdit = model !== null;
  const [form, setForm] = useState<ModelFormState>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm({
      model_id: model?.model_id ?? "",
      display_name: model?.display_name ?? "",
      provider_name: model?.provider_name ?? "Custom",
      category: model?.category ?? "llm",
      model_name: model?.model_name ?? "",
      base_url: model?.base_url ?? "",
      api_key: "",
      pricing_policy_id: model?.pricing_policy_id ?? "",
      max_tokens: String(model?.max_tokens ?? 4096),
      temperature: String(model?.temperature ?? 0.7),
      supports_streaming: model?.supports_streaming ?? true,
      supports_tools: model?.supports_tools ?? false,
      supports_json_mode: model?.supports_json_mode ?? true,
      supports_json_schema: model?.supports_json_schema ?? false,
      supports_vision: model?.supports_vision ?? false,
      supports_reasoning_effort: model?.supports_reasoning_effort ?? false,
      is_default: model?.is_default ?? false,
    });
  }, [open, model]);

  const update = (key: keyof typeof form, value: string | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async () => {
    setError(null);
    setSaving(true);
    try {
      const payload = buildPayload(form);
      if (isEdit) {
        await updateAdminModel(model.model_id, buildUpdatePayload(payload));
      } else {
        await createAdminModel(payload as AdminModelCreatePayload);
      }
      onClose(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(false); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑模型" : "新增模型"}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Model ID" htmlFor="model-id">
            <Input
              id="model-id"
              value={form.model_id}
              disabled={isEdit}
              onChange={(event) => update("model_id", event.target.value)}
            />
          </Field>
          <Field label="显示名" htmlFor="display-name">
            <Input
              id="display-name"
              value={form.display_name}
              onChange={(event) => update("display_name", event.target.value)}
            />
          </Field>
          <Field label="Provider" htmlFor="provider-name">
            <Input
              id="provider-name"
              value={form.provider_name}
              onChange={(event) => update("provider_name", event.target.value)}
            />
          </Field>
          <Field label="类别" htmlFor="category">
            <Select value={form.category} onValueChange={(value) => update("category", value)} disabled={isEdit}>
              <SelectTrigger id="category"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="llm">LLM</SelectItem>
                <SelectItem value="image">Image</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Model Name" htmlFor="model-name">
            <Input
              id="model-name"
              value={form.model_name}
              onChange={(event) => update("model_name", event.target.value)}
            />
          </Field>
          <Field label="Base URL" htmlFor="base-url">
            <Input
              id="base-url"
              value={form.base_url}
              onChange={(event) => update("base_url", event.target.value)}
            />
          </Field>
          <Field label="API Key" htmlFor="api-key">
            <Input
              id="api-key"
              value={form.api_key}
              placeholder={isEdit ? "留空则不更新" : ""}
              onChange={(event) => update("api_key", event.target.value)}
            />
          </Field>
          <Field label="Pricing Policy" htmlFor="pricing-policy">
            <Input
              id="pricing-policy"
              value={form.pricing_policy_id}
              onChange={(event) => update("pricing_policy_id", event.target.value)}
            />
          </Field>
          <Field label="Max Tokens" htmlFor="max-tokens">
            <Input
              id="max-tokens"
              type="number"
              value={form.max_tokens}
              onChange={(event) => update("max_tokens", event.target.value)}
            />
          </Field>
          <Field label="Temperature" htmlFor="temperature">
            <Input
              id="temperature"
              type="number"
              step="0.1"
              value={form.temperature}
              onChange={(event) => update("temperature", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ["supports_streaming", "Streaming"],
            ["supports_tools", "Tools"],
            ["supports_json_mode", "JSON mode"],
            ["supports_json_schema", "JSON schema"],
            ["supports_vision", "Vision"],
            ["supports_reasoning_effort", "Reasoning effort"],
            ["is_default", "设为默认"],
          ].map(([key, label]) => {
            const disabled = key === "is_default" && isEdit && (model?.is_default || !model?.enabled);
            return (
              <label key={key} className="flex items-center gap-2 text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={Boolean(form[key as keyof typeof form])}
                  disabled={disabled}
                  onChange={(event) => update(key as keyof typeof form, event.target.checked)}
                />
                {label}
              </label>
            );
          })}
        </div>

        {error && <div className="text-sm text-rose-600">{error}</div>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={saving}>取消</Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function buildPayload(form: ModelFormState) {
  return {
    model_id: form.model_id.trim(),
    display_name: form.display_name.trim(),
    provider_protocol: "openai_compatible",
    provider_name: form.provider_name.trim() || "Custom",
    category: form.category,
    model_name: form.model_name.trim(),
    base_url: form.base_url.trim(),
    api_key: form.api_key.trim(),
    enabled: true,
    is_default: form.is_default,
    supports_streaming: form.supports_streaming,
    supports_tools: form.supports_tools,
    supports_json_mode: form.supports_json_mode,
    supports_json_schema: form.supports_json_schema,
    supports_vision: form.supports_vision,
    supports_reasoning_effort: form.supports_reasoning_effort,
    max_tokens: parseInt(form.max_tokens, 10) || 4096,
    temperature: parseFloat(form.temperature) || 0.7,
    trust_level: "custom",
    pricing_policy_id: form.pricing_policy_id.trim() || null,
    default_headers: {},
  };
}

function buildUpdatePayload(payload: ReturnType<typeof buildPayload>): AdminModelUpdatePayload {
  const updatePayload: AdminModelUpdatePayload = { ...payload };
  delete updatePayload.api_key;
  delete updatePayload.model_id;
  delete updatePayload.category;
  delete updatePayload.enabled;
  if (payload.api_key) {
    updatePayload.api_key = payload.api_key;
  }
  return updatePayload;
}
