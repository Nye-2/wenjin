"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { AdminPageHeader } from "../../components/AdminPageHeader";
import { CreditRuleDialog } from "./CreditRuleDialog";
import { Button } from "@/components/ui/button";
import {
  deleteCreditRule, listCreditRules, toggleCreditRule, type CreditGrantRule,
} from "@/lib/api/admin-credit-rules";

const RULE_TYPE_LABEL = {
  registration_bonus: "注册奖励",
  referral_referrer: "邀请者奖励",
  referral_referred: "被邀请者奖励",
  periodic: "周期发放",
} as const;

export default function CreditRulesPage() {
  const [rules, setRules] = useState<CreditGrantRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CreditGrantRule | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setLoading(true);
      }
    });
    listCreditRules()
      .then((res) => {
        if (!cancelled) {
          setRules(res.items);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const handleToggle = async (rule: CreditGrantRule) => {
    await toggleCreditRule(rule.id);
    setReloadNonce((v) => v + 1);
  };

  const handleDelete = async (rule: CreditGrantRule) => {
    if (!confirm(`确认删除规则 "${rule.name}"？`)) return;
    await deleteCreditRule(rule.id);
    setReloadNonce((v) => v + 1);
  };

  return (
    <>
      <AdminPageHeader
        title="发放规则"
        description={`共 ${rules.length} 条`}
        actions={
          <Button size="sm" onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> 新建规则
          </Button>
        }
      />

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--border-default)]">
              <th className="px-4 py-3 w-12"></th>
              <th className="px-4 py-3">规则名</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">配置</th>
              <th className="px-4 py-3 text-right">积分</th>
              <th className="px-4 py-3 w-24 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-t border-[var(--border-default)]/50">
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleToggle(rule)}
                    className={`inline-flex w-2.5 h-2.5 rounded-full ${rule.enabled ? "bg-emerald-500" : "bg-slate-400"}`}
                  />
                </td>
                <td className="px-4 py-3 text-[var(--text-primary)]">{rule.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{RULE_TYPE_LABEL[rule.rule_type]}</td>
                <td className="px-4 py-3 text-xs text-[var(--text-muted)] font-mono">
                  {summarizeConfig(rule)}
                </td>
                <td className="px-4 py-3 text-right font-medium">+{rule.amount}</td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button onClick={() => { setEditing(rule); setDialogOpen(true); }} className="text-[var(--accent-primary)] hover:underline">编辑</button>
                  <button onClick={() => handleDelete(rule)} className="text-rose-600 hover:underline">删除</button>
                </td>
              </tr>
            ))}
            {!loading && rules.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-[var(--text-muted)]">暂无规则</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <CreditRuleDialog
        open={dialogOpen}
        rule={editing}
        onClose={(refresh) => {
          setDialogOpen(false);
          setEditing(null);
          if (refresh) setReloadNonce((v) => v + 1);
        }}
      />
    </>
  );
}

function summarizeConfig(rule: CreditGrantRule): string {
  if (rule.rule_type === "periodic") {
    const tf = (rule.config?.target_filter as Record<string, unknown>) ?? {};
    return `${(rule.config?.cron as string) ?? "-"} · 活跃 ${tf.active_within_days ?? "-"} 天 · ${tf.role ?? "-"}`;
  }
  if (rule.rule_type === "referral_referrer") {
    return `trigger: ${rule.config?.trigger as string}`;
  }
  return "";
}
