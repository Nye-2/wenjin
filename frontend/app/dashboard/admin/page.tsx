"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  RefreshCw,
  Users,
  FolderOpen,
  CreditCard,
  TriangleAlert,
} from "lucide-react";

import { Header } from "@/components/layout/header";
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
import { useAuthStore } from "@/stores/auth";
import {
  adminDeductCredits,
  adminGrantCredits,
  getAdminCreditHistory,
  getAdminDashboard,
  getAdminLogs,
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
  type AdminDashboardData,
  type AdminLogItem,
  type AdminUserItem,
  type CreditTransactionItem,
} from "@/lib/api";

type UserRoleFilter = "all" | "user" | "admin";
type UserStatusFilter = "all" | "active" | "inactive";
type CreditTypeFilter =
  | "all"
  | "admin_grant"
  | "admin_deduct"
  | "workflow_consume"
  | "registration_bonus"
  | "refund";
type LogActionFilter =
  | "all"
  | "credit_grant"
  | "credit_deduct"
  | "user_role_change"
  | "user_status_change";
type CreditDialogMode = "grant" | "deduct";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
}

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const responseData = (error as { response?: { data?: unknown } }).response?.data;
    if (responseData && typeof responseData === "object" && "detail" in responseData) {
      const detail = (responseData as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function stringifyLogDetailValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "[unserializable]";
  }
}

function formatLogDetails(details: Record<string, unknown>): string {
  const entries = Object.entries(details);
  if (entries.length === 0) return "-";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${stringifyLogDetailValue(value)}`)
    .join(" | ");
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null);

  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersHasMore, setUsersHasMore] = useState(false);
  const [usersPage, setUsersPage] = useState(1);
  const [usersPageSize, setUsersPageSize] = useState<number>(20);
  const [userKeywordInput, setUserKeywordInput] = useState("");
  const [userKeywordQuery, setUserKeywordQuery] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState<UserRoleFilter>("all");
  const [userStatusFilter, setUserStatusFilter] = useState<UserStatusFilter>("all");

  const [creditHistory, setCreditHistory] = useState<CreditTransactionItem[]>([]);
  const [creditTotal, setCreditTotal] = useState(0);
  const [creditHasMore, setCreditHasMore] = useState(false);
  const [creditPage, setCreditPage] = useState(1);
  const [creditPageSize, setCreditPageSize] = useState<number>(10);
  const [creditTypeFilter, setCreditTypeFilter] = useState<CreditTypeFilter>("all");
  const [creditUserIdInput, setCreditUserIdInput] = useState("");
  const [creditUserIdQuery, setCreditUserIdQuery] = useState("");

  const [adminLogs, setAdminLogs] = useState<AdminLogItem[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logsHasMore, setLogsHasMore] = useState(false);
  const [logsPage, setLogsPage] = useState(1);
  const [logsPageSize, setLogsPageSize] = useState<number>(10);
  const [logActionFilter, setLogActionFilter] = useState<LogActionFilter>("all");
  const [logTargetUserIdInput, setLogTargetUserIdInput] = useState("");
  const [logTargetUserIdQuery, setLogTargetUserIdQuery] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [isCreditLoading, setIsCreditLoading] = useState(false);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoadingUserId, setActionLoadingUserId] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [creditDialogMode, setCreditDialogMode] = useState<CreditDialogMode | null>(null);
  const [creditDialogUser, setCreditDialogUser] = useState<AdminUserItem | null>(null);
  const [creditDialogAmount, setCreditDialogAmount] = useState("100");
  const [creditDialogDescription, setCreditDialogDescription] = useState("");
  const [creditDialogError, setCreditDialogError] = useState<string | null>(null);
  const [creditDialogLoading, setCreditDialogLoading] = useState(false);

  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    if (!authLoading && isAuthenticated && user?.role !== "admin") {
      router.push("/dashboard/me");
    }
  }, [authLoading, isAuthenticated, router, user?.role]);

  useEffect(() => {
    if (!isAuthenticated || user?.role !== "admin") {
      return;
    }

    let cancelled = false;

    const loadData = async () => {
      setError(null);
      if (!hasLoadedOnceRef.current) {
        setIsLoading(true);
      }
      setIsUsersLoading(true);
      setIsCreditLoading(true);
      setIsLogsLoading(true);

      const usersRole = userRoleFilter === "all" ? undefined : userRoleFilter;
      const usersIsActive =
        userStatusFilter === "all" ? undefined : userStatusFilter === "active";
      const creditType = creditTypeFilter === "all" ? undefined : creditTypeFilter;
      const logAction = logActionFilter === "all" ? undefined : logActionFilter;

      const [dashboardRes, usersRes, creditsRes, logsRes] = await Promise.allSettled([
        getAdminDashboard(),
        listAdminUsers({
          page: usersPage,
          page_size: usersPageSize,
          keyword: userKeywordQuery || undefined,
          is_active: usersIsActive,
          role: usersRole,
        }),
        getAdminCreditHistory({
          page: creditPage,
          page_size: creditPageSize,
          user_id: creditUserIdQuery || undefined,
          transaction_type: creditType,
        }),
        getAdminLogs({
          page: logsPage,
          page_size: logsPageSize,
          action: logAction,
          target_user_id: logTargetUserIdQuery || undefined,
        }),
      ]);

      if (cancelled) {
        return;
      }

      let nextError: string | null = null;

      if (dashboardRes.status === "fulfilled") {
        setDashboard(dashboardRes.value);
      } else if (!nextError) {
        nextError = parseErrorMessage(dashboardRes.reason, "加载概览失败");
      }

      if (usersRes.status === "fulfilled") {
        setUsers(usersRes.value.users);
        setUsersTotal(usersRes.value.total);
        setUsersHasMore(usersRes.value.has_more);
      } else if (!nextError) {
        nextError = parseErrorMessage(usersRes.reason, "加载用户列表失败");
      }

      if (creditsRes.status === "fulfilled") {
        setCreditHistory(creditsRes.value.transactions);
        setCreditTotal(creditsRes.value.total);
        setCreditHasMore(creditsRes.value.has_more);
      } else if (!nextError) {
        nextError = parseErrorMessage(creditsRes.reason, "加载积分流水失败");
      }

      if (logsRes.status === "fulfilled") {
        setAdminLogs(logsRes.value.logs);
        setLogsTotal(logsRes.value.total);
        setLogsHasMore(logsRes.value.has_more);
      } else if (!nextError) {
        nextError = parseErrorMessage(logsRes.reason, "加载管理员日志失败");
      }

      setError(nextError);
      setIsLoading(false);
      setIsRefreshing(false);
      setIsUsersLoading(false);
      setIsCreditLoading(false);
      setIsLogsLoading(false);
      hasLoadedOnceRef.current = true;
    };

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [
    isAuthenticated,
    user?.role,
    reloadNonce,
    usersPage,
    usersPageSize,
    userKeywordQuery,
    userRoleFilter,
    userStatusFilter,
    creditPage,
    creditPageSize,
    creditTypeFilter,
    creditUserIdQuery,
    logsPage,
    logsPageSize,
    logActionFilter,
    logTargetUserIdQuery,
  ]);

  const runUserAction = async (userId: string, action: () => Promise<void>) => {
    setActionLoadingUserId(userId);
    setError(null);
    try {
      await action();
      setReloadNonce((value) => value + 1);
    } catch (err) {
      setError(parseErrorMessage(err, "操作失败"));
    } finally {
      setActionLoadingUserId(null);
    }
  };

  const openCreditDialog = (mode: CreditDialogMode, targetUser: AdminUserItem) => {
    setCreditDialogMode(mode);
    setCreditDialogUser(targetUser);
    setCreditDialogAmount("100");
    setCreditDialogDescription(mode === "grant" ? "管理员发放积分" : "管理员扣除积分");
    setCreditDialogError(null);
  };

  const closeCreditDialog = (force = false) => {
    if (creditDialogLoading && !force) return;
    setCreditDialogMode(null);
    setCreditDialogUser(null);
    setCreditDialogAmount("100");
    setCreditDialogDescription("");
    setCreditDialogError(null);
  };

  const submitCreditDialog = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!creditDialogMode || !creditDialogUser) {
      return;
    }

    const amountValue = Number(creditDialogAmount);
    if (!Number.isFinite(amountValue) || !Number.isInteger(amountValue) || amountValue <= 0) {
      setCreditDialogError("积分数量必须是正整数");
      return;
    }

    setCreditDialogError(null);
    setCreditDialogLoading(true);
    try {
      const description =
        creditDialogDescription.trim() ||
        (creditDialogMode === "grant" ? "管理员发放积分" : "管理员扣除积分");

      if (creditDialogMode === "grant") {
        await adminGrantCredits({
          user_id: creditDialogUser.id,
          amount: amountValue,
          description,
        });
      } else {
        await adminDeductCredits({
          user_id: creditDialogUser.id,
          amount: amountValue,
          description,
        });
      }
      closeCreditDialog(true);
      setReloadNonce((value) => value + 1);
    } catch (err) {
      setCreditDialogError(parseErrorMessage(err, "积分操作失败"));
    } finally {
      setCreditDialogLoading(false);
    }
  };

  if (authLoading || (isLoading && !dashboard)) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
      </main>
    );
  }

  if (!isAuthenticated || user?.role !== "admin") {
    return null;
  }

  const usersStart = usersTotal === 0 ? 0 : (usersPage - 1) * usersPageSize + 1;
  const usersEnd = Math.min(usersTotal, usersPage * usersPageSize);
  const creditsStart = creditTotal === 0 ? 0 : (creditPage - 1) * creditPageSize + 1;
  const creditsEnd = Math.min(creditTotal, creditPage * creditPageSize);
  const logsStart = logsTotal === 0 ? 0 : (logsPage - 1) * logsPageSize + 1;
  const logsEnd = Math.min(logsTotal, logsPage * logsPageSize);

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8 pt-24 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold text-[var(--text-primary)]">管理仪表盘</h1>
            <p className="text-[var(--text-secondary)] mt-1">
              用户、任务与积分系统的运行概览
            </p>
          </div>
          <button
            onClick={() => {
              setIsRefreshing(true);
              setReloadNonce((value) => value + 1);
            }}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-primary)] hover:bg-[var(--bg-surface)] transition-colors disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2">
            <TriangleAlert className="w-4 h-4" />
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">总用户数</span>
              <Users className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.summary.users.total ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              活跃 {dashboard?.summary.users.active ?? 0} / 管理员 {dashboard?.summary.users.admins ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">工作空间</span>
              <FolderOpen className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.summary.workspaces.total ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              任务运行中 {dashboard?.summary.tasks.running ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">积分流通</span>
              <CreditCard className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.summary.credits.in_circulation ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              发放 {dashboard?.summary.credits.total_issued ?? 0} / 消费 {dashboard?.summary.credits.total_spent ?? 0}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">24h 失败任务</span>
              <TriangleAlert className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div className="mt-3 text-3xl font-bold text-[var(--text-primary)]">
              {dashboard?.summary.tasks.failed_last_24h ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              全量任务 {dashboard?.summary.tasks.total ?? 0}
            </div>
          </div>
        </div>

        <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">用户管理</h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                显示 {usersStart}-{usersEnd} / 共 {usersTotal}
              </p>
            </div>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setUsersPage(1);
                setUserKeywordQuery(userKeywordInput.trim());
              }}
            >
              <div className="min-w-52">
                <Label htmlFor="users-keyword" className="text-xs text-[var(--text-muted)] mb-1 block">
                  关键词（邮箱/用户名）
                </Label>
                <Input
                  id="users-keyword"
                  value={userKeywordInput}
                  onChange={(event) => setUserKeywordInput(event.target.value)}
                  placeholder="输入后点击查询"
                  className="h-9"
                />
              </div>
              <div className="w-32">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">角色</Label>
                <Select
                  value={userRoleFilter}
                  onValueChange={(value) => {
                    setUsersPage(1);
                    setUserRoleFilter(value as UserRoleFilter);
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部</SelectItem>
                    <SelectItem value="admin">管理员</SelectItem>
                    <SelectItem value="user">普通用户</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-32">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">状态</Label>
                <Select
                  value={userStatusFilter}
                  onValueChange={(value) => {
                    setUsersPage(1);
                    setUserStatusFilter(value as UserStatusFilter);
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部</SelectItem>
                    <SelectItem value="active">正常</SelectItem>
                    <SelectItem value="inactive">禁用</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-28">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">每页条数</Label>
                <Select
                  value={String(usersPageSize)}
                  onValueChange={(value) => {
                    setUsersPage(1);
                    setUsersPageSize(Number(value));
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <SelectItem key={size} value={String(size)}>
                        {size}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" size="sm">
                查询
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setUserKeywordInput("");
                  setUserKeywordQuery("");
                  setUsersPage(1);
                  setUserRoleFilter("all");
                  setUserStatusFilter("all");
                }}
              >
                重置
              </Button>
            </form>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border-default)]">
                  <th className="py-2">邮箱</th>
                  <th className="py-2">角色</th>
                  <th className="py-2">状态</th>
                  <th className="py-2">积分</th>
                  <th className="py-2">注册时间</th>
                  <th className="py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((item) => {
                  const busy = actionLoadingUserId === item.id;
                  return (
                    <tr key={item.id} className="border-b border-[var(--border-default)]/50">
                      <td className="py-2 text-[var(--text-primary)]">{item.email}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{item.role}</td>
                      <td className="py-2">
                        <span
                          className={`px-2 py-1 rounded-md text-xs ${
                            item.is_active
                              ? "bg-emerald-500/10 text-emerald-600"
                              : "bg-rose-500/10 text-rose-600"
                          }`}
                        >
                          {item.is_active ? "正常" : "禁用"}
                        </span>
                      </td>
                      <td className="py-2 text-[var(--text-primary)]">{item.credits}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.created_at)}</td>
                      <td className="py-2">
                        <div className="flex flex-wrap gap-2">
                          <button
                            disabled={busy}
                            onClick={() => openCreditDialog("grant", item)}
                            className="px-2 py-1 rounded-md text-xs bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 disabled:opacity-60"
                          >
                            发放
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => openCreditDialog("deduct", item)}
                            className="px-2 py-1 rounded-md text-xs bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 disabled:opacity-60"
                          >
                            扣除
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void runUserAction(item.id, async () => {
                                await updateAdminUserRole(
                                  item.id,
                                  item.role === "admin" ? "user" : "admin"
                                );
                              })
                            }
                            className="px-2 py-1 rounded-md text-xs bg-blue-500/10 text-blue-600 hover:bg-blue-500/20 disabled:opacity-60"
                          >
                            {item.role === "admin" ? "设为用户" : "设为管理员"}
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void runUserAction(item.id, async () => {
                                await updateAdminUserStatus(item.id, !item.is_active);
                              })
                            }
                            className="px-2 py-1 rounded-md text-xs bg-rose-500/10 text-rose-600 hover:bg-rose-500/20 disabled:opacity-60"
                          >
                            {item.is_active ? "禁用" : "启用"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {isUsersLoading && (
              <div className="text-sm text-[var(--text-muted)] py-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载用户数据
              </div>
            )}
            {users.length === 0 && (
              <div className="text-sm text-[var(--text-muted)] py-3">暂无用户数据</div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">第 {usersPage} 页</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={usersPage <= 1 || isUsersLoading}
                  onClick={() => setUsersPage((value) => Math.max(1, value - 1))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!usersHasMore || isUsersLoading}
                  onClick={() => setUsersPage((value) => value + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">积分流水</h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                显示 {creditsStart}-{creditsEnd} / 共 {creditTotal}
              </p>
            </div>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setCreditPage(1);
                setCreditUserIdQuery(creditUserIdInput.trim());
              }}
            >
              <div className="min-w-52">
                <Label
                  htmlFor="credits-user-id"
                  className="text-xs text-[var(--text-muted)] mb-1 block"
                >
                  用户 ID
                </Label>
                <Input
                  id="credits-user-id"
                  value={creditUserIdInput}
                  onChange={(event) => setCreditUserIdInput(event.target.value)}
                  placeholder="按用户 ID 过滤"
                  className="h-9"
                />
              </div>
              <div className="w-44">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">交易类型</Label>
                <Select
                  value={creditTypeFilter}
                  onValueChange={(value) => {
                    setCreditPage(1);
                    setCreditTypeFilter(value as CreditTypeFilter);
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部</SelectItem>
                    <SelectItem value="admin_grant">admin_grant</SelectItem>
                    <SelectItem value="admin_deduct">admin_deduct</SelectItem>
                    <SelectItem value="workflow_consume">workflow_consume</SelectItem>
                    <SelectItem value="registration_bonus">registration_bonus</SelectItem>
                    <SelectItem value="refund">refund</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-28">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">每页条数</Label>
                <Select
                  value={String(creditPageSize)}
                  onValueChange={(value) => {
                    setCreditPage(1);
                    setCreditPageSize(Number(value));
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <SelectItem key={size} value={String(size)}>
                        {size}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" size="sm">
                查询
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setCreditPage(1);
                  setCreditUserIdInput("");
                  setCreditUserIdQuery("");
                  setCreditTypeFilter("all");
                }}
              >
                重置
              </Button>
            </form>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border-default)]">
                  <th className="py-2">时间</th>
                  <th className="py-2">用户</th>
                  <th className="py-2">类型</th>
                  <th className="py-2">变动</th>
                  <th className="py-2">余额</th>
                  <th className="py-2">描述</th>
                </tr>
              </thead>
              <tbody>
                {creditHistory.map((item) => (
                  <tr key={item.id} className="border-b border-[var(--border-default)]/50">
                    <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.created_at)}</td>
                    <td className="py-2 text-[var(--text-primary)]">{item.user_email ?? item.user_id ?? "-"}</td>
                    <td className="py-2 text-[var(--text-secondary)]">{item.type}</td>
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
            {isCreditLoading && (
              <div className="text-sm text-[var(--text-muted)] py-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载积分流水
              </div>
            )}
            {creditHistory.length === 0 && (
              <div className="text-sm text-[var(--text-muted)] py-3">暂无积分流水</div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">第 {creditPage} 页</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={creditPage <= 1 || isCreditLoading}
                  onClick={() => setCreditPage((value) => Math.max(1, value - 1))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!creditHasMore || isCreditLoading}
                  onClick={() => setCreditPage((value) => value + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">管理员日志</h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                显示 {logsStart}-{logsEnd} / 共 {logsTotal}
              </p>
            </div>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setLogsPage(1);
                setLogTargetUserIdQuery(logTargetUserIdInput.trim());
              }}
            >
              <div className="min-w-52">
                <Label
                  htmlFor="logs-target-user-id"
                  className="text-xs text-[var(--text-muted)] mb-1 block"
                >
                  目标用户 ID
                </Label>
                <Input
                  id="logs-target-user-id"
                  value={logTargetUserIdInput}
                  onChange={(event) => setLogTargetUserIdInput(event.target.value)}
                  placeholder="按目标用户 ID 过滤"
                  className="h-9"
                />
              </div>
              <div className="w-44">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">操作类型</Label>
                <Select
                  value={logActionFilter}
                  onValueChange={(value) => {
                    setLogsPage(1);
                    setLogActionFilter(value as LogActionFilter);
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部</SelectItem>
                    <SelectItem value="credit_grant">credit_grant</SelectItem>
                    <SelectItem value="credit_deduct">credit_deduct</SelectItem>
                    <SelectItem value="user_role_change">user_role_change</SelectItem>
                    <SelectItem value="user_status_change">user_status_change</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-28">
                <Label className="text-xs text-[var(--text-muted)] mb-1 block">每页条数</Label>
                <Select
                  value={String(logsPageSize)}
                  onValueChange={(value) => {
                    setLogsPage(1);
                    setLogsPageSize(Number(value));
                  }}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <SelectItem key={size} value={String(size)}>
                        {size}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" size="sm">
                查询
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setLogsPage(1);
                  setLogTargetUserIdInput("");
                  setLogTargetUserIdQuery("");
                  setLogActionFilter("all");
                }}
              >
                重置
              </Button>
            </form>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border-default)]">
                  <th className="py-2">时间</th>
                  <th className="py-2">操作</th>
                  <th className="py-2">管理员</th>
                  <th className="py-2">目标用户</th>
                  <th className="py-2">详情</th>
                </tr>
              </thead>
              <tbody>
                {adminLogs.map((item) => (
                  <tr key={item.id} className="border-b border-[var(--border-default)]/50">
                    <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.created_at)}</td>
                    <td className="py-2 text-[var(--text-primary)]">{item.action}</td>
                    <td className="py-2 text-[var(--text-secondary)]">
                      {item.admin?.email ?? item.admin_id ?? "-"}
                    </td>
                    <td className="py-2 text-[var(--text-secondary)]">
                      {item.target_user?.email ?? item.target_user_id ?? "-"}
                    </td>
                    <td className="py-2 text-[var(--text-secondary)]">{formatLogDetails(item.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isLogsLoading && (
              <div className="text-sm text-[var(--text-muted)] py-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载管理员日志
              </div>
            )}
            {adminLogs.length === 0 && (
              <div className="text-sm text-[var(--text-muted)] py-3">暂无管理员日志</div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">第 {logsPage} 页</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={logsPage <= 1 || isLogsLoading}
                  onClick={() => setLogsPage((value) => Math.max(1, value - 1))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!logsHasMore || isLogsLoading}
                  onClick={() => setLogsPage((value) => value + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <Dialog
        open={creditDialogMode !== null && creditDialogUser !== null}
        onOpenChange={(open) => {
          if (!open) {
            closeCreditDialog();
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {creditDialogMode === "grant" ? "发放积分" : "扣除积分"}
            </DialogTitle>
            <DialogDescription>
              {creditDialogUser
                ? `目标用户：${creditDialogUser.email}`
                : "请设置积分数量与操作原因"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitCreditDialog} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="credit-dialog-amount">积分数量（正整数）</Label>
              <Input
                id="credit-dialog-amount"
                type="number"
                min={1}
                step={1}
                value={creditDialogAmount}
                onChange={(event) => setCreditDialogAmount(event.target.value)}
                disabled={creditDialogLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="credit-dialog-description">原因说明</Label>
              <Input
                id="credit-dialog-description"
                value={creditDialogDescription}
                onChange={(event) => setCreditDialogDescription(event.target.value)}
                placeholder="请输入原因"
                maxLength={500}
                disabled={creditDialogLoading}
              />
            </div>
            {creditDialogError && (
              <div className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg p-2">
                {creditDialogError}
              </div>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => closeCreditDialog()}
                disabled={creditDialogLoading}
              >
                取消
              </Button>
              <Button type="submit" disabled={creditDialogLoading}>
                {creditDialogLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {creditDialogMode === "grant" ? "确认发放" : "确认扣除"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
