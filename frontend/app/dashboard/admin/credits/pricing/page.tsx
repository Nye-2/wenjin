"use client";

import { useEffect, useState } from "react";
import { Plus, ShieldAlert } from "lucide-react";

import { AdminPageHeader } from "../../components/AdminPageHeader";
import { PricingPolicyDialog } from "./PricingPolicyDialog";
import { PricingSimulator } from "./PricingSimulator";
import { Button } from "@/components/ui/button";
import { disablePricingPolicy, listPricingPolicies } from "@/lib/api/admin-pricing";
import type { AdminPricingPolicy } from "@/lib/api/types";

export default function AdminPricingPage() {
  const [policies, setPolicies] = useState<AdminPricingPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AdminPricingPolicy | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) setLoading(true);
    });
    listPricingPolicies()
      .then((response) => {
        if (!cancelled) setPolicies(response.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "定价策略加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const refresh = () => setReloadNonce((value) => value + 1);

  const handleDisable = async (policy: AdminPricingPolicy) => {
    setError(null);
    await disablePricingPolicy(policy.policy_key);
    refresh();
  };

  return (
    <>
      <AdminPageHeader
        title="定价策略"
        description={`共 ${policies.length} 条`}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="w-4 h-4 mr-1" /> 新增策略
          </Button>
        }
      />

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <ShieldAlert className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="mb-5">
        <PricingSimulator />
      </div>

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--border-default)]">
              <th className="px-4 py-3">策略</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">配置摘要</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.policy_key} className="border-t border-[var(--border-default)]/50 align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-[var(--text-primary)]">{policy.name}</div>
                  <div className="mt-1 flex gap-2 text-xs text-[var(--text-muted)]">
                    <span className="font-mono">{policy.policy_key}</span>
                    <span>v{policy.version}</span>
                    {!policy.enabled && <span className="text-slate-500">停用</span>}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-[var(--text-secondary)]">{policy.policy_kind}</td>
                <td className="px-4 py-3 text-xs text-[var(--text-muted)]">
                  {summarizeConfig(policy.config)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(policy);
                        setDialogOpen(true);
                      }}
                      className="text-[var(--accent-primary)] hover:underline"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDisable(policy)}
                      className="text-rose-600 hover:underline"
                    >
                      停用
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!loading && policies.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-[var(--text-muted)]">
                  暂无定价策略
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <PricingPolicyDialog
        open={dialogOpen}
        policy={editing}
        onClose={(refreshList) => {
          setDialogOpen(false);
          setEditing(null);
          if (refreshList) refresh();
        }}
      />
    </>
  );
}

function summarizeConfig(config: Record<string, unknown>): string {
  const entries = Object.entries(config).slice(0, 4);
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${key}: ${formatValue(value)}`).join(" · ");
}

function formatValue(value: unknown): string {
  if (typeof value === "object" && value !== null) return "{...}";
  return String(value);
}
