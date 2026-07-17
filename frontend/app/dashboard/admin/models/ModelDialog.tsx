"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createAdminModel,
  updateAdminModel,
  type AdminModelCreatePayload,
  type AdminModelUpdatePayload,
} from "@/lib/api/admin-models";
import { listPricingPolicies } from "@/lib/api/admin-pricing";
import type {
  AdminModelCatalogItem,
  AdminPricingPolicy,
} from "@/lib/api/types";

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
  enabled: true,
  is_default: false,
};

type ModelFormState = typeof INITIAL_FORM;
type HeaderRow = {
  id: string;
  key: string;
  value: string;
  redacted: boolean;
};

const NO_PRICING_POLICY = "__none__";
const REDACTED_VALUE = "[redacted]";

export function ModelDialog({ open, model, onClose }: Props) {
  const isEdit = model !== null;
  const [form, setForm] = useState<ModelFormState>(INITIAL_FORM);
  const [pricingPolicies, setPricingPolicies] = useState<AdminPricingPolicy[]>(
    [],
  );
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>([]);
  const [headersTouched, setHeadersTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setHeadersTouched(false);
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
      enabled: model?.enabled ?? true,
      is_default: model?.is_default ?? false,
    });
    setHeaderRows(headersToRows(model?.default_headers ?? {}));
    listPricingPolicies({ policy_kind: "model_usage", enabled_only: true })
      .then((response) => setPricingPolicies(response.items))
      .catch((err) => {
        setPricingPolicies([]);
        setError(err instanceof Error ? err.message : "定价策略加载失败");
      });
  }, [open, model]);

  const update = (key: keyof typeof form, value: string | boolean) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "is_default" && value === true) {
        next.enabled = true;
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    setError(null);
    if (headersTouched && hasUnresolvedRedactedHeaders(headerRows)) {
      setError("存在已脱敏 Header，修改 Headers 前请重新填写或删除该行。");
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(form, headersToPayload(headerRows));
      if (isEdit) {
        await updateAdminModel(
          model.model_id,
          buildUpdatePayload(payload, headersTouched),
        );
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

  const addHeaderRow = () => {
    setHeadersTouched(true);
    setHeaderRows((current) => [
      ...current,
      { id: nextHeaderRowId(), key: "", value: "", redacted: false },
    ]);
  };

  const updateHeaderRow = (id: string, key: "key" | "value", value: string) => {
    setHeadersTouched(true);
    setHeaderRows((current) =>
      current.map((row) =>
        row.id === id ? { ...row, [key]: value, redacted: false } : row,
      ),
    );
  };

  const removeHeaderRow = (id: string) => {
    setHeadersTouched(true);
    setHeaderRows((current) => current.filter((row) => row.id !== id));
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose(false);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑模型" : "新增模型"}</DialogTitle>
          <DialogDescription>
            配置 OpenAI-compatible 模型入口、默认 header 和计费策略绑定。
            密钥字段只写入或轮换，保存后不会回显明文。
          </DialogDescription>
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
            <Select
              value={form.category}
              onValueChange={(value) => update("category", value)}
              disabled={isEdit}
            >
              <SelectTrigger id="category">
                <SelectValue />
              </SelectTrigger>
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
              type="password"
              autoComplete="new-password"
              value={form.api_key}
              placeholder={isEdit ? "已配置时留空则不更新；填写新值会轮换" : ""}
              onChange={(event) => update("api_key", event.target.value)}
            />
          </Field>
          <Field label="Pricing Policy" htmlFor="pricing-policy">
            <Select
              value={form.pricing_policy_id || NO_PRICING_POLICY}
              onValueChange={(value) =>
                update(
                  "pricing_policy_id",
                  value === NO_PRICING_POLICY ? "" : value,
                )
              }
            >
              <SelectTrigger id="pricing-policy">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_PRICING_POLICY}>未绑定</SelectItem>
                {pricingPolicies.map((policy) => (
                  <SelectItem key={policy.policy_key} value={policy.policy_key}>
                    {policy.name} · {policy.policy_key}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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

        <div className="space-y-3 rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-[var(--wjn-text)]">
                Default Headers
              </div>
              <div className="text-xs text-[var(--wjn-text-muted)]">
                敏感 header 只可写入或轮换，后台不会回显明文。
              </div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={addHeaderRow}
            >
              <Plus className="mr-1 h-4 w-4" />
              添加 Header
            </Button>
          </div>
          {headerRows.length > 0 ? (
            <div className="space-y-2">
              {headerRows.map((row, index) => (
                <div
                  key={row.id}
                  className="grid grid-cols-[1fr_1fr_auto] items-end gap-2"
                >
                  <Field
                    label={`Header Key ${index + 1}`}
                    htmlFor={`header-key-${row.id}`}
                  >
                    <Input
                      id={`header-key-${row.id}`}
                      value={row.key}
                      placeholder="api-key"
                      onChange={(event) =>
                        updateHeaderRow(row.id, "key", event.target.value)
                      }
                    />
                  </Field>
                  <Field
                    label={`Header Value ${index + 1}`}
                    htmlFor={`header-value-${row.id}`}
                  >
                    <Input
                      id={`header-value-${row.id}`}
                      value={row.value}
                      placeholder={
                        row.redacted ? "已配置，留空则不改" : "header value"
                      }
                      type={isSensitiveHeaderKey(row.key) ? "password" : "text"}
                      onChange={(event) =>
                        updateHeaderRow(row.id, "value", event.target.value)
                      }
                    />
                  </Field>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={`删除 Header ${index + 1}`}
                    onClick={() => removeHeaderRow(row.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-[var(--wjn-line)] px-3 py-4 text-center text-xs text-[var(--wjn-text-muted)]">
              没有自定义 header。
            </div>
          )}
        </div>

        {isEdit && (
          <div className="rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-3 text-sm">
            <div className="font-medium text-[var(--wjn-text)]">探测能力</div>
            <div className="mt-1 text-xs text-[var(--wjn-text-muted)]">
              能力只来自最近一次端点探测。修改模型名、地址、协议、密钥或 Header 后，旧探测会立即失效；请保存后在模型列表重新测试。
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ["enabled", "启用"],
            ["is_default", "设为默认"],
          ].map(([key, label]) => {
            const disabled =
              (key === "is_default" &&
                isEdit &&
                (model?.is_default || !form.enabled)) ||
              (key === "enabled" && form.is_default);
            return (
              <label
                key={key}
                className="flex items-center gap-2 text-[var(--wjn-text-secondary)]"
              >
                <input
                  type="checkbox"
                  checked={Boolean(form[key as keyof typeof form])}
                  disabled={disabled}
                  onChange={(event) =>
                    update(key as keyof typeof form, event.target.checked)
                  }
                />
                {label}
              </label>
            );
          })}
        </div>

        {error && <div className="text-sm text-rose-600">{error}</div>}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onClose(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function buildPayload(
  form: ModelFormState,
  defaultHeaders: Record<string, unknown>,
) {
  return {
    model_id: form.model_id.trim(),
    display_name: form.display_name.trim(),
    generation_api: form.category === "llm" ? "chat_completions" as const : null,
    provider_name: form.provider_name.trim() || "Custom",
    category: form.category,
    model_name: form.model_name.trim(),
    base_url: form.base_url.trim(),
    api_key: form.api_key.trim(),
    enabled: form.enabled,
    is_default: form.is_default,
    max_tokens: parsePositiveInteger(form.max_tokens, 4096),
    temperature: parseFiniteNumber(form.temperature, 0.7),
    trust_level: "custom",
    pricing_policy_id: form.pricing_policy_id.trim() || null,
    default_headers: defaultHeaders,
  };
}

function parsePositiveInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseFiniteNumber(value: string, fallback: number): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildUpdatePayload(
  payload: ReturnType<typeof buildPayload>,
  headersTouched: boolean,
): AdminModelUpdatePayload {
  const updatePayload: AdminModelUpdatePayload = { ...payload };
  delete updatePayload.api_key;
  delete updatePayload.model_id;
  delete updatePayload.category;
  if (!headersTouched) {
    delete updatePayload.default_headers;
  }
  if (payload.api_key) {
    updatePayload.api_key = payload.api_key;
  }
  return updatePayload;
}

function headersToRows(headers: Record<string, unknown>): HeaderRow[] {
  return Object.entries(headers).map(([key, value], index) => {
    const valueText = value == null ? "" : String(value);
    const redacted = valueText === REDACTED_VALUE;
    return {
      id: `existing-${index}-${key}`,
      key,
      value: redacted ? "" : valueText,
      redacted,
    };
  });
}

function headersToPayload(rows: HeaderRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((acc, row) => {
    const key = row.key.trim();
    const value = row.value.trim();
    if (!key || !value || value === REDACTED_VALUE) {
      return acc;
    }
    acc[key] = value;
    return acc;
  }, {});
}

function hasUnresolvedRedactedHeaders(rows: HeaderRow[]): boolean {
  return rows.some(
    (row) => row.redacted && row.key.trim().length > 0 && !row.value.trim(),
  );
}

function nextHeaderRowId(): string {
  return `new-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isSensitiveHeaderKey(key: string): boolean {
  return /(authorization|api[-_\s]?key|access[-_\s]?key|secret|token|password|credential)/i.test(
    key,
  );
}
