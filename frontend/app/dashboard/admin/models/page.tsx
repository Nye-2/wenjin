"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, FlaskConical, Plus, ShieldAlert } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { ModelDialog } from "./ModelDialog";
import { Button } from "@/components/ui/button";
import {
  disableAdminModel,
  listAdminModels,
  setDefaultAdminModel,
  testAdminModel,
  updateAdminModel,
} from "@/lib/api/admin-models";
import type { AdminModelCatalogItem } from "@/lib/api/types";

export default function AdminModelsPage() {
  const [models, setModels] = useState<AdminModelCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AdminModelCatalogItem | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) setLoading(true);
    });
    listAdminModels()
      .then((response) => {
        if (!cancelled) setModels(response.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "模型列表加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const refresh = () => setReloadNonce((value) => value + 1);

  const handleDisable = async (model: AdminModelCatalogItem) => {
    setError(null);
    if (model.is_default) {
      setError("默认模型不能直接禁用，请先设置新的默认模型。");
      return;
    }
    await disableAdminModel(model.model_id);
    refresh();
  };

  const handleEnable = async (model: AdminModelCatalogItem) => {
    setError(null);
    await updateAdminModel(model.model_id, { enabled: true });
    refresh();
  };

  const handleDefault = async (model: AdminModelCatalogItem) => {
    setError(null);
    if (!model.enabled) {
      setError("停用模型不能设为默认，请先启用该模型。");
      return;
    }
    await setDefaultAdminModel(model.model_id);
    refresh();
  };

  const handleTest = async (model: AdminModelCatalogItem) => {
    setError(null);
    await testAdminModel(model.model_id);
    refresh();
  };

  return (
    <>
      <AdminPageHeader
        title="模型管理"
        description={`共 ${models.length} 个模型`}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="w-4 h-4 mr-1" /> 新增模型
          </Button>
        }
      />

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <ShieldAlert className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--wjn-line)]">
              <th className="px-4 py-3">模型</th>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">API</th>
              <th className="px-4 py-3">能力</th>
              <th className="px-4 py-3">定价</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.model_id} className="border-t border-[var(--wjn-line)]/50 align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-[var(--wjn-text)]">{model.display_name}</div>
                  <div className="mt-1 flex flex-wrap gap-1 text-xs text-[var(--wjn-text-muted)]">
                    <span>{model.model_id}</span>
                    <span>·</span>
                    <span>{model.model_name}</span>
                    {model.is_default && (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700">默认</span>
                    )}
                    {!model.enabled && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">停用</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-[var(--wjn-text-secondary)]">
                  <div>{model.provider_name}</div>
                  <div className="text-xs text-[var(--wjn-text-muted)]">{model.category}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-56 truncate text-[var(--wjn-text-secondary)]">{model.base_url}</div>
                  <div className="font-mono text-xs text-[var(--wjn-text-muted)]">
                    {model.api_key_redacted ?? "未设置"}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-[var(--wjn-text-secondary)]">
                  {summarizeCapabilities(model)}
                  <div className="mt-1 flex items-center gap-1">
                    {model.health_status === "healthy" && <CheckCircle2 className="w-3 h-3 text-emerald-600" />}
                    <span>{model.health_status}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--wjn-text-muted)]">
                  {model.pricing_policy_id || "未绑定"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      aria-label={`测试 ${model.model_id}`}
                      onClick={() => handleTest(model)}
                      className="text-[var(--wjn-navy)] hover:underline"
                    >
                      <FlaskConical className="inline h-3.5 w-3.5" /> 测试
                    </button>
                    <button
                      type="button"
                      aria-label={`编辑 ${model.model_id}`}
                      onClick={() => {
                        setEditing(model);
                        setDialogOpen(true);
                      }}
                      className="text-[var(--wjn-navy)] hover:underline"
                    >
                      编辑
                    </button>
                    {!model.is_default && model.enabled && (
                      <button
                        type="button"
                        aria-label={`设为默认 ${model.model_id}`}
                        onClick={() => handleDefault(model)}
                        className="text-[var(--wjn-navy)] hover:underline"
                      >
                        默认
                      </button>
                    )}
                    {model.enabled ? (
                      <button
                        type="button"
                        aria-label={`禁用 ${model.model_id}`}
                        onClick={() => handleDisable(model)}
                        className="text-rose-600 hover:underline"
                      >
                        禁用
                      </button>
                    ) : (
                      <button
                        type="button"
                        aria-label={`启用 ${model.model_id}`}
                        onClick={() => handleEnable(model)}
                        className="text-[var(--wjn-navy)] hover:underline"
                      >
                        启用
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && models.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[var(--wjn-text-muted)]">
                  暂无模型
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <ModelDialog
        open={dialogOpen}
        model={editing}
        onClose={(refreshList) => {
          setDialogOpen(false);
          setEditing(null);
          if (refreshList) refresh();
        }}
      />
    </>
  );
}

function summarizeCapabilities(model: AdminModelCatalogItem): string {
  const items = [
    model.supports_streaming ? "stream" : null,
    model.supports_tools ? "tools" : null,
    model.supports_json_schema ? "schema" : model.supports_json_mode ? "json" : null,
    model.supports_vision ? "vision" : null,
    model.supports_reasoning_effort ? "reasoning" : null,
  ].filter(Boolean);
  return items.length ? items.join(" · ") : "basic";
}
