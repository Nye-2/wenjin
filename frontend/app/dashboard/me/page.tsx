"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  RefreshCw,
  CreditCard,
  FolderKanban,
  ListChecks,
  TrendingUp,
  Gauge,
  Gift,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import {
  formatCreditCostLabel,
  formatCreditTransactionType,
  getThreadCreditStatus,
  renderCostValue,
  summarizeCreditTransaction,
} from "@/lib/credit-display";
import { useAuthStore } from "@/stores/auth";
import {
  getMyCreditHistory,
  getMyDashboard,
  redeemCreditCode,
  type CreditTransactionItem,
  type UserDashboardData,
} from "@/lib/api";

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
}

export default function MyDashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user, setUser } = useAuthStore();

  const [dashboard, setDashboard] = useState<UserDashboardData | null>(null);
  const [history, setHistory] = useState<CreditTransactionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [redeemCode, setRedeemCode] = useState("");
  const [isRedeeming, setIsRedeeming] = useState(false);
  const [redeemMessage, setRedeemMessage] = useState<string | null>(null);
  const [redeemError, setRedeemError] = useState<string | null>(null);

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
      return { dashboardData, historyData };
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
      return null;
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleRedeemCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const code = redeemCode.trim();
    if (!code) {
      setRedeemError("请输入兑换码");
      setRedeemMessage(null);
      return;
    }

    setIsRedeeming(true);
    setRedeemError(null);
    setRedeemMessage(null);
    try {
      const result = await redeemCreditCode(code);
      setRedeemCode("");
      setRedeemMessage(`兑换成功，已到账 ${result.amount.toLocaleString()} 积分。`);
      const refreshed = await loadDashboard(true);
      if (user) {
        const refreshedCredits = refreshed?.dashboardData.credits;
        setUser({
          ...user,
          credits: refreshedCredits?.balance ?? result.balance_after,
          total_credits_earned:
            refreshedCredits?.total_earned ?? user.total_credits_earned,
          total_credits_spent:
            refreshedCredits?.total_spent ?? user.total_credits_spent,
        });
      }
    } catch (err) {
      setRedeemError(err instanceof Error ? err.message : "兑换失败，请检查兑换码");
    } finally {
      setIsRedeeming(false);
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
  const creditBalance = dashboard?.credits.balance ?? 0;
  const threadCredit = getThreadCreditStatus(dashboard?.credits);
  const completionRate = ((dashboard?.tasks.completion_rate ?? 0) * 100).toFixed(1);
  const recentTasks = dashboard?.recent_tasks ?? [];

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="route-topography max-w-7xl mx-auto px-4 py-8 pt-24 space-y-6">
        <div className="route-card rounded-[1.75rem] p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--accent-secondary)]">
              账户总览
            </p>
            <h1 className="mt-3 text-3xl font-bold text-[var(--text-primary)]">账户概览</h1>
            <p className="text-[var(--text-secondary)] mt-1">
              查看积分、任务与工作空间状态，保持你的研究工作线索清晰可追踪。
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

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
          <div
            className={`rounded-[1.5rem] border p-5 ${
              creditBalance < 0
                ? "border-rose-500/30 bg-rose-500/10"
                : "route-card"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">当前积分</span>
              <CreditCard className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div
              className={`mt-3 text-3xl font-bold ${
                creditBalance < 0 ? "text-rose-600" : "text-[var(--text-primary)]"
              }`}
            >
              {creditBalance.toLocaleString()}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              累计获得 {dashboard?.credits.total_earned ?? 0} / 累计消费 {dashboard?.credits.total_spent ?? 0}
            </div>
            {threadCredit?.overdraft_credits ? (
              <div className="mt-2 text-xs text-rose-600">
                已透支 {threadCredit.overdraft_credits} 积分，补充积分后可恢复主线对话。
              </div>
            ) : null}
          </div>

          <div className="route-card rounded-[1.5rem] p-5">
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

          <div className="route-card rounded-[1.5rem] p-5">
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

          <div className="route-card rounded-[1.5rem] p-5">
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

          <div className="route-card rounded-[1.5rem] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">主线状态</span>
              <Gauge className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {threadCredit?.can_start_thread ? "可用" : "暂停"}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              按实际使用折算积分
            </div>
          </div>
        </div>

        <section className="route-card rounded-[1.75rem] p-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--wjn-accent-soft)] text-[var(--accent-primary)]">
                  <Gift className="h-4 w-4" />
                </span>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">兑换码充值</h2>
              </div>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                输入管理员发放的 credits 兑换码，成功后会立即写入积分流水，并刷新账户余额。
              </p>
            </div>

            <form onSubmit={handleRedeemCode} className="w-full max-w-xl">
              <label
                htmlFor="credit-redeem-code"
                className="text-xs font-medium text-[var(--text-muted)]"
              >
                兑换码
              </label>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input
                  id="credit-redeem-code"
                  value={redeemCode}
                  onChange={(event) => setRedeemCode(event.target.value)}
                  placeholder="输入兑换码"
                  className="min-h-11 flex-1 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:ring-4 focus:ring-[var(--accent-primary)]/10"
                />
                <button
                  type="submit"
                  disabled={isRedeeming}
                  className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--accent-primary)] px-5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
                >
                  {isRedeeming ? "兑换中..." : "立即兑换"}
                </button>
              </div>
              {redeemMessage ? (
                <div className="mt-2 text-sm text-emerald-600">{redeemMessage}</div>
              ) : null}
              {redeemError ? (
                <div className="mt-2 text-sm text-rose-600">{redeemError}</div>
              ) : null}
            </form>
          </div>
        </section>

        {threadCredit?.enabled ? (
          <section
            className={`rounded-2xl border p-5 ${
              threadCredit.can_start_thread
                ? "route-card"
                : "border-amber-500/30 bg-amber-500/10"
            }`}
          >
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">主线对话计费状态</h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  主线对话按实际使用自动折算为积分，账单只展示积分扣减。
                </p>
              </div>
              <div
                className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
                  threadCredit.can_start_thread
                    ? "bg-emerald-500/10 text-emerald-600"
                    : "bg-rose-500/10 text-rose-600"
                }`}
              >
                {threadCredit.can_start_thread ? "主线对话可用" : "主线对话已暂停"}
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                <div className="text-xs text-[var(--text-muted)]">计费单位</div>
                <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                  积分
                </div>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                <div className="text-xs text-[var(--text-muted)]">扣费方式</div>
                <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                  自动折算
                </div>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                <div className="text-xs text-[var(--text-muted)]">当前透支</div>
                <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                  {threadCredit.overdraft_credits.toLocaleString()} 积分
                </div>
              </div>
            </div>
            {!threadCredit.can_start_thread ? (
              <div className="mt-4 text-sm text-rose-600">
                当前轮次已允许结算，但下一次主线对话会被拦截。请先补充积分后再继续推进。
              </div>
            ) : null}
          </section>
        ) : null}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <section className="route-card rounded-[1.75rem] p-5">
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
                      <td className="py-2 text-[var(--text-primary)]">{formatCreditCostLabel(key)}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{renderCostValue(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="route-card rounded-[1.75rem] p-5">
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

        <section className="route-card rounded-[1.75rem] p-5">
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
                    <td className="py-2 text-[var(--text-primary)]">{formatCreditTransactionType(item.type)}</td>
                    <td
                      className={`py-2 font-medium ${
                        item.amount >= 0 ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      {item.amount >= 0 ? `+${item.amount}` : item.amount}
                    </td>
                    <td
                      className={`py-2 ${
                        item.balance_after < 0 ? "text-rose-600" : "text-[var(--text-primary)]"
                      }`}
                    >
                      {item.balance_after}
                    </td>
                    <td className="py-2 text-[var(--text-secondary)]">
                      {summarizeCreditTransaction(item)}
                    </td>
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
