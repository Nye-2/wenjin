"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, RefreshCw, CreditCard, FolderKanban, ListChecks, TrendingUp } from "lucide-react";

import { Header } from "@/components/layout/header";
import { useAuthStore } from "@/stores/auth";
import {
  getMyCreditHistory,
  getMyDashboard,
  type CreditCostValue,
  type CreditTransactionItem,
  type UserDashboardData,
} from "@/lib/api";

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
}

function renderCostValue(value: CreditCostValue): string {
  if (typeof value === "number") return `${value}`;
  const parts = Object.entries(value).map(([k, v]) =>
    `${k}: ${typeof v === "boolean" ? (v ? "on" : "off") : v}`
  );
  return parts.join(" | ");
}

export default function MyDashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [dashboard, setDashboard] = useState<UserDashboardData | null>(null);
  const [history, setHistory] = useState<CreditTransactionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = async (refresh = false) => {
    if (refresh) setIsRefreshing(true);
    if (!refresh) setIsLoading(true);
    setError(null);

    try {
      const [dashboardData, historyData] = await Promise.all([
        getMyDashboard(),
        getMyCreditHistory({ page: 1, page_size: 20 }),
      ]);
      setDashboard(dashboardData);
      setHistory(historyData.transactions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) {
      void loadDashboard();
    }
  }, [isAuthenticated]);

  if (authLoading || (isLoading && !dashboard)) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
      </main>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const costs = dashboard?.credits.costs ?? {};
  const completionRate = ((dashboard?.tasks.completion_rate ?? 0) * 100).toFixed(1);
  const recentTasks = dashboard?.recent_tasks ?? [];

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8 pt-24 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold text-[var(--text-primary)]">个人仪表盘</h1>
            <p className="text-[var(--text-secondary)] mt-1">
              查看积分、任务与工作空间总体状态
            </p>
          </div>
          <button
            onClick={() => void loadDashboard(true)}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-primary)] hover:bg-[var(--bg-surface)] transition-colors disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">当前积分</span>
              <CreditCard className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.credits.balance ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              累计获得 {dashboard?.credits.total_earned ?? 0} / 累计消费 {dashboard?.credits.total_spent ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">工作空间</span>
              <FolderKanban className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.workspaces.total ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              近 7 天新增 {dashboard?.workspaces.created_last_7d ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">任务总数</span>
              <ListChecks className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.tasks.total ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              运行中 {dashboard?.tasks.running ?? 0} / 失败 {dashboard?.tasks.failed ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">任务完成率</span>
              <TrendingUp className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {completionRate}%
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              成功 {dashboard?.tasks.success ?? 0}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">模块积分标准</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border-default)]">
                    <th className="py-2">模块</th>
                    <th className="py-2">消耗</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(costs).map(([key, value]) => (
                    <tr key={key} className="border-b border-[var(--border-default)]/50">
                      <td className="py-2 text-[var(--text-primary)]">{key}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{renderCostValue(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">最近任务</h2>
            <div className="mt-4 space-y-3">
              {recentTasks.length ? (
                recentTasks.map((task) => (
                  <div
                    key={task.id}
                    className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-[var(--text-primary)]">{task.task_type}</span>
                      <span className="text-xs text-[var(--text-muted)]">{task.status}</span>
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-secondary)]">
                      进度 {task.progress}% · {formatDate(task.created_at)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-[var(--text-muted)]">暂无任务记录</div>
              )}
            </div>
          </section>
        </div>

        <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">积分流水</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border-default)]">
                  <th className="py-2">时间</th>
                  <th className="py-2">类型</th>
                  <th className="py-2">变动</th>
                  <th className="py-2">余额</th>
                  <th className="py-2">描述</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id} className="border-b border-[var(--border-default)]/50">
                    <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.created_at)}</td>
                    <td className="py-2 text-[var(--text-primary)]">{item.type}</td>
                    <td
                      className={`py-2 font-medium ${
                        item.amount >= 0 ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      {item.amount >= 0 ? `+${item.amount}` : item.amount}
                    </td>
                    <td className="py-2 text-[var(--text-primary)]">{item.balance_after}</td>
                    <td className="py-2 text-[var(--text-secondary)]">{item.description ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {history.length === 0 && (
              <div className="text-sm text-[var(--text-muted)] py-3">暂无积分流水</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
