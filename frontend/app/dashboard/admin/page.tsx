"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  Coins,
  CreditCard,
  FolderOpen,
  Gauge,
  TriangleAlert,
  Users,
} from "lucide-react";

import { AdminPageHeader } from "./components/AdminPageHeader";
import { getAdminDashboard, type AdminDashboardData } from "@/lib/api";

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export default function AdminOverviewPage() {
  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setIsLoading(true);
        setError(null);
      }
    });
    getAdminDashboard()
      .then((data) => {
        if (!cancelled) setDashboard(data);
      })
      .catch((err) => {
        if (!cancelled) setError(parseErrorMessage(err, "加载概览失败"));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const overdraftUsers = dashboard?.summary.credits.overdraft_users ?? 0;
  const hasOverdraft = overdraftUsers > 0;
  const tokenUsage = dashboard?.summary.token_usage;

  return (
    <>
      <AdminPageHeader
        title="管理总览"
        description="用户、任务、积分与系统配置的运行概览。"
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2 mb-4">
          <TriangleAlert className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
        <SummaryCard
          icon={<Users className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="总用户数"
          value={dashboard?.summary.users.total ?? 0}
          hint={`活跃 ${dashboard?.summary.users.active ?? 0} / 管理员 ${dashboard?.summary.users.admins ?? 0}`}
        />
        <SummaryCard
          icon={<FolderOpen className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="工作空间"
          value={dashboard?.summary.workspaces.total ?? 0}
          hint={`任务运行中 ${dashboard?.summary.tasks.running ?? 0}`}
        />
        <SummaryCard
          icon={<CreditCard className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="积分余额池"
          value={dashboard?.summary.credits.in_circulation ?? 0}
          hint={`发放 ${dashboard?.summary.credits.total_issued ?? 0} / 消费 ${dashboard?.summary.credits.total_spent ?? 0}`}
          variant={hasOverdraft ? "danger" : "default"}
        />
        <SummaryCard
          icon={<TriangleAlert className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="透支用户"
          value={overdraftUsers}
          hint={`累计透支 ${dashboard?.summary.credits.overdraft_credits_total ?? 0} 积分`}
          variant={hasOverdraft ? "danger" : "default"}
        />
        <SummaryCard
          icon={<TriangleAlert className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="24h 失败任务"
          value={dashboard?.summary.tasks.failed_last_24h ?? 0}
          hint={`全量任务 ${dashboard?.summary.tasks.total ?? 0}`}
        />
        <SummaryCard
          icon={<Gauge className="w-5 h-5 text-[var(--wjn-navy)]" />}
          label="Token 用量"
          value={tokenUsage?.thread.total_tokens ?? 0}
          hint="thread tokens（累计）"
        />
      </div>

      {tokenUsage ? (
        <section className="route-card rounded-2xl border p-5 mb-6">
          <h2 className="text-lg font-semibold text-[var(--wjn-text)]">Token 用量观测</h2>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-3">
              <div className="text-xs text-[var(--wjn-text-muted)]">主线对话</div>
              <div className="mt-1 text-lg font-semibold text-[var(--wjn-text)]">
                {tokenUsage.thread.total_tokens.toLocaleString()}
              </div>
              <div className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">
                结算 {tokenUsage.thread.transactions} 笔 / 用户 {tokenUsage.thread.users}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-3">
              <div className="text-xs text-[var(--wjn-text-muted)]">子代理</div>
              <div className="mt-1 text-lg font-semibold text-[var(--wjn-text)]">
                {tokenUsage.subagents.total_tokens.toLocaleString()}
              </div>
              <div className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">
                记录 {tokenUsage.subagents.records_with_usage}/{tokenUsage.subagents.records}
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {hasOverdraft ? (
        <section className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700 mb-6">
          当前有 {overdraftUsers} 个账号处于负余额，总计透支 {dashboard?.summary.credits.overdraft_credits_total ?? 0} 积分。
          这些用户当前轮次允许完成结算，但下一次纯主线对话会被拦截；要恢复使用，直接补发积分即可。
        </section>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <AnalyticsEntryCard href="/dashboard/admin/users" title="用户管理" icon={<Users className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/credits" title="积分流水" icon={<Coins className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/mcp" title="MCP 配置" icon={<BarChart3 className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/release-gate" title="发布门禁" icon={<FolderOpen className="w-5 h-5" />} />
      </div>
    </>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
  variant = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  hint: string;
  variant?: "default" | "danger";
}) {
  const isDanger = variant === "danger";
  return (
    <div className={`rounded-2xl border p-5 ${isDanger ? "border-rose-500/30 bg-rose-500/10" : "route-card"}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--wjn-text-secondary)]">{label}</span>
        {icon}
      </div>
      <div className={`mt-3 text-3xl font-bold ${isDanger ? "text-rose-600" : "text-[var(--wjn-text)]"}`}>
        {value.toLocaleString()}
      </div>
      <div className="mt-1 text-xs text-[var(--wjn-text-muted)]">{hint}</div>
    </div>
  );
}

function AnalyticsEntryCard({ href, title, icon }: { href: string; title: string; icon: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="route-card rounded-2xl p-5 flex items-center gap-3 hover:bg-[var(--wjn-surface)] transition-colors"
    >
      <div className="text-[var(--wjn-navy)]">{icon}</div>
      <div className="text-sm font-medium text-[var(--wjn-text)]">{title}</div>
    </Link>
  );
}
