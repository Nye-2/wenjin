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
  ShieldCheck,
  ShieldX,
  Download,
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
import {
  formatCreditTransactionType,
  summarizeCreditTransaction,
} from "@/lib/credit-display";
import { useAuthStore } from "@/stores/auth";
import {
  adminDeductCredits,
  adminGrantCredits,
  getAdminCreditHistory,
  getAdminDashboard,
  getAdminReleaseGate,
  getAdminLogs,
  getMcpConfig,
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
  updateMcpConfig,
  type AdminDashboardData,
  type AdminLogItem,
  type ReleaseGateCheck,
  type AdminReleaseGateReport,
  type AdminUserItem,
  type CreditTransactionItem,
  type McpConfigResponse,
  type McpServerConfigInput,
} from "@/lib/api";

type UserRoleFilter = "all" | "user" | "admin";
type UserStatusFilter = "all" | "active" | "inactive";
type CreditTypeFilter =
  | "all"
  | "admin_grant"
  | "admin_deduct"
  | "workflow_consume"
  | "chat_token_consume"
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

function exportRowsToCsv(
  filename: string,
  headers: string[],
  rows: Array<Array<string | number | boolean | null | undefined>>
) {
  const escapeCell = (value: string | number | boolean | null | undefined) => {
    const text = value === null || value === undefined ? "" : String(value);
    return `"${text.replace(/"/g, '""')}"`;
  };

  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCell).join(","))
    .join("\n");

  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function formatJsonDraft(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseMcpServersDraft(draft: string): Record<string, McpServerConfigInput> {
  const parsed = JSON.parse(draft || "{}") as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP 配置必须是一个 JSON 对象，key 为 server 名称。");
  }
  return parsed as Record<string, McpServerConfigInput>;
}

function getCheckStatusClass(status: ReleaseGateCheck["status"]): string {
  if (status === "passed") return "bg-emerald-500/10 text-emerald-600";
  if (status === "failed") return "bg-rose-500/10 text-rose-600";
  if (status === "pending") return "bg-amber-500/10 text-amber-600";
  return "bg-slate-500/10 text-slate-600";
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null);
  const [releaseGateReport, setReleaseGateReport] = useState<AdminReleaseGateReport | null>(null);
  const [mcpConfig, setMcpConfig] = useState<McpConfigResponse | null>(null);
  const [mcpDraft, setMcpDraft] = useState("{}");
  const [mcpDraftBaseline, setMcpDraftBaseline] = useState("{}");
  const [mcpDraftError, setMcpDraftError] = useState<string | null>(null);

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
  const [isMcpLoading, setIsMcpLoading] = useState(false);
  const [isMcpSaving, setIsMcpSaving] = useState(false);
  const [isReleaseGateRunning, setIsReleaseGateRunning] = useState(false);
  const [releaseGateError, setReleaseGateError] = useState<string | null>(null);
  const [releaseGateFilterFailed, setReleaseGateFilterFailed] = useState(false);
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
      setIsMcpLoading(true);

      const usersRole = userRoleFilter === "all" ? undefined : userRoleFilter;
      const usersIsActive =
        userStatusFilter === "all" ? undefined : userStatusFilter === "active";
      const creditType = creditTypeFilter === "all" ? undefined : creditTypeFilter;
      const logAction = logActionFilter === "all" ? undefined : logActionFilter;

      const [dashboardRes, usersRes, creditsRes, logsRes, mcpRes] = await Promise.allSettled([
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
        getMcpConfig(),
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

      if (mcpRes.status === "fulfilled") {
        const formattedDraft = formatJsonDraft(mcpRes.value.mcp_servers ?? {});
        setMcpConfig(mcpRes.value);
        setMcpDraft(formattedDraft);
        setMcpDraftBaseline(formattedDraft);
        setMcpDraftError(null);
      } else if (!nextError) {
        nextError = parseErrorMessage(mcpRes.reason, "加载 MCP 配置失败");
      }

      setError(nextError);
      setIsLoading(false);
      setIsRefreshing(false);
      setIsUsersLoading(false);
      setIsCreditLoading(false);
      setIsLogsLoading(false);
      setIsMcpLoading(false);
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

  const runReleaseGate = async (includeExtended: boolean) => {
    setReleaseGateError(null);
    setIsReleaseGateRunning(true);
    try {
      const report = await getAdminReleaseGate({ include_extended: includeExtended });
      setReleaseGateReport(report);
    } catch (err) {
      setReleaseGateError(parseErrorMessage(err, "发布门禁执行失败"));
    } finally {
      setIsReleaseGateRunning(false);
    }
  };

  const exportReleaseGateJSON = () => {
    if (!releaseGateReport) return;
    const blob = new Blob([JSON.stringify(releaseGateReport, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `release-gate-${releaseGateReport.generated_at.replace(/[: ]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportUsersCsv = () => {
    exportRowsToCsv(
      `admin-users-${new Date().toISOString().slice(0, 10)}.csv`,
      [
        "email",
        "name",
        "role",
        "is_active",
        "credits",
        "is_overdraft",
        "overdraft_credits",
        "workspace_count",
        "task_count",
        "created_at",
        "last_login",
      ],
      users.map((item) => [
        item.email,
        item.name ?? "",
        item.role,
        item.is_active ? "active" : "inactive",
        item.credits,
        item.credits < 0 ? "yes" : "no",
        item.credits < 0 ? Math.abs(item.credits) : 0,
        item.workspace_count,
        item.task_count,
        item.created_at ?? "",
        item.last_login ?? "",
      ])
    );
  };

  const exportCreditsCsv = () => {
    exportRowsToCsv(
      `admin-credit-history-${new Date().toISOString().slice(0, 10)}.csv`,
      ["created_at", "user_email", "user_id", "type", "amount", "balance_after", "description"],
      creditHistory.map((item) => [
        item.created_at,
        item.user_email ?? "",
        item.user_id ?? "",
        formatCreditTransactionType(item.type),
        item.amount,
        item.balance_after,
        summarizeCreditTransaction(item),
      ])
    );
  };

  const exportLogsCsv = () => {
    exportRowsToCsv(
      `admin-logs-${new Date().toISOString().slice(0, 10)}.csv`,
      ["created_at", "action", "admin_email", "target_user_email", "target_user_id", "details"],
      adminLogs.map((item) => [
        item.created_at,
        item.action,
        item.admin?.email ?? item.admin_id ?? "",
        item.target_user?.email ?? "",
        item.target_user_id ?? "",
        formatLogDetails(item.details),
      ])
    );
  };

  const formatMcpDraft = () => {
    try {
      const parsed = parseMcpServersDraft(mcpDraft);
      setMcpDraft(formatJsonDraft(parsed));
      setMcpDraftError(null);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "MCP 配置 JSON 无法格式化"));
    }
  };

  const restoreMcpDraft = () => {
    setMcpDraft(mcpDraftBaseline);
    setMcpDraftError(null);
  };

  const saveMcpDraft = async () => {
    let parsedServers: Record<string, McpServerConfigInput>;
    try {
      parsedServers = parseMcpServersDraft(mcpDraft);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "MCP 配置 JSON 无效"));
      return;
    }

    setMcpDraftError(null);
    setIsMcpSaving(true);
    try {
      const nextConfig = await updateMcpConfig({ mcp_servers: parsedServers });
      const formattedDraft = formatJsonDraft(nextConfig.mcp_servers ?? {});
      setMcpConfig(nextConfig);
      setMcpDraft(formattedDraft);
      setMcpDraftBaseline(formattedDraft);
    } catch (err) {
      setMcpDraftError(parseErrorMessage(err, "保存 MCP 配置失败"));
    } finally {
      setIsMcpSaving(false);
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
  const mcpServerEntries = Object.entries(mcpConfig?.mcp_servers ?? {});
  const enabledMcpCount = mcpServerEntries.filter(([, config]) => config.enabled !== false).length;
  const hasMcpChanges = mcpDraft.trim() !== mcpDraftBaseline.trim();
  const coreChecks = releaseGateReport?.core_gate.checks ?? [];
  const extendedChecks = releaseGateReport?.extended_gate.checks ?? [];
  const failedChecks = [...coreChecks, ...extendedChecks].filter(
    (check) => check.status === "failed" || check.status === "missing"
  );
  const isFailed = (s: string) => s === "failed" || s === "missing";
  const visibleCoreChecks = releaseGateFilterFailed ? coreChecks.filter((c) => isFailed(c.status)) : coreChecks;
  const visibleExtendedChecks = releaseGateFilterFailed ? extendedChecks.filter((c) => isFailed(c.status)) : extendedChecks;
  const overdraftUsers = dashboard?.summary.credits.overdraft_users ?? 0;
  const overdraftCreditsTotal = dashboard?.summary.credits.overdraft_credits_total ?? 0;
  const manualDeductions = dashboard?.summary.credits.manual_deductions ?? 0;
  const hasOverdraftUsers = overdraftUsers > 0;
  let mcpDraftPreviewError: string | null = null;
  try {
    parseMcpServersDraft(mcpDraft);
  } catch (err) {
    mcpDraftPreviewError = parseErrorMessage(err, "MCP 配置 JSON 无效");
  }

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="route-topography max-w-7xl mx-auto px-4 py-8 pt-24 space-y-6">
        <div className="route-card rounded-[1.75rem] p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--accent-secondary)]">
              管理总览
            </p>
            <h1 className="mt-3 text-3xl font-bold text-[var(--text-primary)]">管理总览</h1>
            <p className="text-[var(--text-secondary)] mt-1">
              用户、任务、积分与系统配置的运行概览。
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

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
          <div className="route-card rounded-[1.5rem] p-5">
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

          <div className="route-card rounded-[1.5rem] p-5">
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

          <div
            className={`rounded-2xl border p-5 ${
              hasOverdraftUsers
                ? "border-rose-500/30 bg-rose-500/10"
                : "route-card"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">积分余额池</span>
              <CreditCard className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div
              className={`mt-3 text-3xl font-bold ${
                hasOverdraftUsers ? "text-rose-600" : "text-[var(--text-primary)]"
              }`}
            >
              {dashboard?.summary.credits.in_circulation ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              发放 {dashboard?.summary.credits.total_issued ?? 0} / 消费 {dashboard?.summary.credits.total_spent ?? 0}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              管理员扣减 {manualDeductions}
            </div>
          </div>

          <div
            className={`rounded-2xl border p-5 ${
              hasOverdraftUsers
                ? "border-rose-500/30 bg-rose-500/10"
                : "route-card"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">透支用户</span>
              <TriangleAlert className="w-5 h-5 text-[var(--accent-primary)]" />
            </div>
            <div
              className={`mt-3 text-3xl font-bold ${
                hasOverdraftUsers ? "text-rose-600" : "text-[var(--text-primary)]"
              }`}
            >
              {overdraftUsers}
            </div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              累计透支 {overdraftCreditsTotal} 积分
            </div>
          </div>

          <div className="route-card rounded-[1.5rem] p-5">
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

        {hasOverdraftUsers ? (
          <section className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700">
            当前有 {overdraftUsers} 个账号处于负余额，总计透支 {overdraftCreditsTotal} 积分。
            这些用户当前轮次允许完成结算，但下一次纯主线对话会被拦截；要恢复使用，直接补发积分即可。
          </section>
        ) : null}

        <section className="route-card rounded-[1.75rem] p-5">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">发布门禁（Release Gate）</h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                手动执行核心 / 扩展检查，输出 Go / No-Go 报告
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={isReleaseGateRunning}
                onClick={() => void runReleaseGate(false)}
              >
                {isReleaseGateRunning ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
                运行核心门禁
              </Button>
              <Button
                size="sm"
                disabled={isReleaseGateRunning}
                onClick={() => void runReleaseGate(true)}
              >
                {isReleaseGateRunning ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
                运行核心 + 扩展检查
              </Button>
            </div>
          </div>

          {releaseGateError && (
            <div className="mt-3 rounded-lg border border-rose-300/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-600">
              {releaseGateError}
            </div>
          )}

          {!releaseGateReport ? (
            <div className="mt-4 rounded-lg border border-dashed border-[var(--border-default)] px-3 py-4 text-sm text-[var(--text-muted)]">
              尚未执行门禁检查。点击上方按钮生成报告。
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${
                    releaseGateReport.status === "passed"
                      ? "bg-emerald-500/10 text-emerald-600"
                      : "bg-rose-500/10 text-rose-600"
                  }`}
                >
                  {releaseGateReport.status === "passed" ? (
                    <ShieldCheck className="w-3.5 h-3.5" />
                  ) : (
                    <ShieldX className="w-3.5 h-3.5" />
                  )}
                  {releaseGateReport.go_no_go.toUpperCase()}
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  生成时间：{formatDate(releaseGateReport.generated_at)}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[var(--text-primary)]">核心门禁</span>
                    <span
                      className={`text-xs ${
                        releaseGateReport.core_gate.status === "passed"
                          ? "text-emerald-600"
                          : "text-rose-600"
                      }`}
                    >
                      {releaseGateReport.core_gate.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    通过 {releaseGateReport.core_gate.passed} / 失败 {releaseGateReport.core_gate.failed} / 缺失 {releaseGateReport.core_gate.missing}
                  </p>
                </div>
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[var(--text-primary)]">扩展检查</span>
                    <span
                      className={`text-xs ${
                        releaseGateReport.extended_gate.status === "passed"
                          ? "text-emerald-600"
                          : releaseGateReport.extended_gate.status === "pending"
                            ? "text-amber-600"
                            : "text-rose-600"
                      }`}
                    >
                      {releaseGateReport.extended_gate.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    通过 {releaseGateReport.extended_gate.passed} / 失败 {releaseGateReport.extended_gate.failed} / 缺失 {releaseGateReport.extended_gate.missing}
                  </p>
                </div>
              </div>

              {releaseGateReport.recommendations.length > 0 && (
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">修复建议</h3>
                  <div className="mt-2 space-y-1">
                    {releaseGateReport.recommendations.slice(0, 5).map((item, index) => (
                      <p key={`${item}-${index}`} className="text-xs text-[var(--text-secondary)]">
                        {index + 1}. {item}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">检查明细</h3>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--text-muted)]">
                      总计 {coreChecks.length + extendedChecks.length} 项，失败/缺失 {failedChecks.length} 项
                    </span>
                    <button
                      type="button"
                      onClick={() => setReleaseGateFilterFailed((prev) => !prev)}
                      className={`rounded px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        releaseGateFilterFailed
                          ? "bg-rose-500/15 text-rose-600"
                          : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                      }`}
                    >
                      {releaseGateFilterFailed ? "仅失败/缺失" : "全部"}
                    </button>
                    <button
                      type="button"
                      onClick={exportReleaseGateJSON}
                      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                      title="导出 JSON 报告"
                    >
                      <Download className="w-3 h-3" />
                      导出
                    </button>
                  </div>
                </div>

                {visibleCoreChecks.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-[var(--text-secondary)]">核心门禁</p>
                    <div className="space-y-2">
                      {visibleCoreChecks.map((check) => (
                        <details
                          key={`core-${check.id}`}
                          className="rounded-lg border border-[var(--border-default)] px-3 py-2"
                        >
                          <summary className="cursor-pointer list-none">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-medium text-[var(--text-primary)]">
                                {check.id}
                              </span>
                              <span className={`rounded px-2 py-0.5 text-[11px] ${getCheckStatusClass(check.status)}`}>
                                {check.status}
                              </span>
                              {typeof check.runtime?.duration_seconds === "number" && (
                                <span className="text-[11px] text-[var(--text-muted)]">
                                  {check.runtime.duration_seconds}s
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-[var(--text-muted)]">{check.description}</p>
                          </summary>
                          {(check.runtime?.output_tail || check.fix_hint || check.runtime?.command) && (
                            <div className="mt-2 space-y-2 border-t border-[var(--border-default)] pt-2">
                              {check.runtime?.command && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  命令：<code>{check.runtime.command}</code>
                                </p>
                              )}
                              {check.runtime?.return_code !== undefined && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  返回码：{check.runtime.return_code}
                                </p>
                              )}
                              {check.fix_hint && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  建议：{check.fix_hint}
                                </p>
                              )}
                              {check.runtime?.output_tail && (
                                <pre className="max-h-44 overflow-auto rounded-md bg-[var(--bg-base)] p-2 text-[11px] text-[var(--text-secondary)]">
                                  {check.runtime.output_tail}
                                </pre>
                              )}
                            </div>
                          )}
                        </details>
                      ))}
                    </div>
                  </div>
                )}

                {visibleExtendedChecks.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-[var(--text-secondary)]">扩展检查</p>
                    <div className="space-y-2">
                      {visibleExtendedChecks.map((check) => (
                        <details
                          key={`extended-${check.id}`}
                          className="rounded-lg border border-[var(--border-default)] px-3 py-2"
                        >
                          <summary className="cursor-pointer list-none">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-medium text-[var(--text-primary)]">
                                {check.id}
                              </span>
                              <span className={`rounded px-2 py-0.5 text-[11px] ${getCheckStatusClass(check.status)}`}>
                                {check.status}
                              </span>
                              {typeof check.runtime?.duration_seconds === "number" && (
                                <span className="text-[11px] text-[var(--text-muted)]">
                                  {check.runtime.duration_seconds}s
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-[var(--text-muted)]">{check.description}</p>
                          </summary>
                          {(check.runtime?.output_tail || check.fix_hint || check.runtime?.command) && (
                            <div className="mt-2 space-y-2 border-t border-[var(--border-default)] pt-2">
                              {check.runtime?.command && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  命令：<code>{check.runtime.command}</code>
                                </p>
                              )}
                              {check.runtime?.return_code !== undefined && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  返回码：{check.runtime.return_code}
                                </p>
                              )}
                              {check.fix_hint && (
                                <p className="text-[11px] text-[var(--text-secondary)]">
                                  建议：{check.fix_hint}
                                </p>
                              )}
                              {check.runtime?.output_tail && (
                                <pre className="max-h-44 overflow-auto rounded-md bg-[var(--bg-base)] p-2 text-[11px] text-[var(--text-secondary)]">
                                  {check.runtime.output_tail}
                                </pre>
                              )}
                            </div>
                          )}
                        </details>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>

        <section className="route-card rounded-[1.75rem] p-5">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">MCP 配置中心</h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                管理外部 MCP server。编辑区只修改 <code>mcp_servers</code>，不会覆盖 skills 配置。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setIsRefreshing(true);
                  setReloadNonce((value) => value + 1);
                }}
                disabled={isRefreshing || isMcpSaving}
              >
                <RefreshCw className={`w-4 h-4 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
                重新加载
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={formatMcpDraft}
                disabled={isMcpLoading || isMcpSaving}
              >
                格式化 JSON
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={restoreMcpDraft}
                disabled={isMcpSaving || !hasMcpChanges}
              >
                撤销改动
              </Button>
              <Button
                size="sm"
                onClick={() => void saveMcpDraft()}
                disabled={isMcpSaving || !hasMcpChanges || Boolean(mcpDraftPreviewError)}
              >
                {isMcpSaving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
                保存配置
              </Button>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
              <div className="text-xs text-[var(--text-muted)]">服务数量</div>
              <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                {mcpServerEntries.length}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
              <div className="text-xs text-[var(--text-muted)]">启用中的服务</div>
              <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                {enabledMcpCount}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
              <div className="text-xs text-[var(--text-muted)]">当前草稿状态</div>
              <div className="mt-2 text-sm font-medium text-[var(--text-primary)]">
                {hasMcpChanges ? "有未保存改动" : "与已加载配置一致"}
              </div>
              <div className="mt-1 text-xs text-[var(--text-muted)]">
                {mcpDraftPreviewError ? "JSON 需修复后才能保存" : "可直接保存并触发 runtime 热更新"}
              </div>
            </div>
          </div>

          {isMcpLoading ? (
            <div className="mt-4 text-sm text-[var(--text-muted)] flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              正在加载 MCP 配置
            </div>
          ) : mcpServerEntries.length === 0 ? (
            <div className="mt-4 rounded-xl border border-dashed border-[var(--border-default)] px-4 py-5 text-sm text-[var(--text-muted)]">
              当前没有配置任何 MCP 服务。可在下方 JSON 草稿中添加，例如：
              <pre className="mt-2 overflow-x-auto rounded-lg bg-[var(--bg-base)] p-3 text-[11px] text-[var(--text-secondary)]">
{`{
  "github": {
    "enabled": true,
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"]
  }
}`}
              </pre>
            </div>
          ) : (
            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-3">
              {mcpServerEntries.map(([name, server]) => (
                <div
                  key={name}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{name}</h3>
                      <p className="text-xs text-[var(--text-muted)] mt-1">
                        {server.description?.trim() || "未填写说明"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-[var(--bg-muted)] px-2 py-1 text-[11px] text-[var(--text-secondary)]">
                        {server.type ?? "stdio"}
                      </span>
                      <span
                        className={`rounded-md px-2 py-1 text-[11px] ${
                          server.enabled === false
                            ? "bg-rose-500/10 text-rose-600"
                            : "bg-emerald-500/10 text-emerald-600"
                        }`}
                      >
                        {server.enabled === false ? "已禁用" : "已启用"}
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 space-y-2 text-xs text-[var(--text-secondary)]">
                    {server.command ? <p>命令: <code>{server.command}</code></p> : null}
                    {server.url ? <p>地址: <code>{server.url}</code></p> : null}
                    {server.args?.length ? <p>参数: <code>{server.args.join(" ")}</code></p> : null}
                    {server.headers && Object.keys(server.headers).length > 0 ? (
                      <p>请求头: {Object.keys(server.headers).join(", ")}</p>
                    ) : null}
                    <p>
                      鉴权:{" "}
                      {server.oauth?.enabled === false
                        ? "已禁用"
                        : server.oauth
                          ? `已启用（${server.oauth.grant_type ?? "client_credentials"}）`
                          : "未配置"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-5 space-y-2">
            <Label htmlFor="mcp-config-draft" className="text-sm font-medium text-[var(--text-primary)]">
              MCP Server 草稿
            </Label>
            <textarea
              id="mcp-config-draft"
              value={mcpDraft}
              onChange={(event) => {
                setMcpDraft(event.target.value);
                if (mcpDraftError) {
                  setMcpDraftError(null);
                }
              }}
              spellCheck={false}
              className="min-h-[320px] w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] px-4 py-3 font-mono text-xs text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--accent-primary)]"
            />
            <p className="text-[11px] text-[var(--text-muted)]">
              保存后会写入后端 `extensions_config.json`，并立即刷新 MCP runtime 与工具缓存。
            </p>
            {(mcpDraftError || mcpDraftPreviewError) && (
              <div className="rounded-lg border border-rose-300/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-600">
                {mcpDraftError ?? mcpDraftPreviewError}
              </div>
            )}
          </div>
        </section>

        <section className="route-card rounded-[1.75rem] p-5">
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
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={exportUsersCsv}
                disabled={users.length === 0}
              >
                <Download className="w-4 h-4 mr-1" />
                导出 CSV
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
                  <th className="py-2">工作区</th>
                  <th className="py-2">任务</th>
                  <th className="py-2">注册时间</th>
                  <th className="py-2">最后登录</th>
                  <th className="py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((item) => {
                  const busy = actionLoadingUserId === item.id;
                  const isOverdraft = item.credits < 0;
                  return (
                    <tr
                      key={item.id}
                      className={`border-b border-[var(--border-default)]/50 ${
                        isOverdraft ? "bg-rose-500/5" : ""
                      }`}
                    >
                      <td className="py-2 text-[var(--text-primary)]">
                        <div className="flex items-center gap-2">
                          <span>{item.email}</span>
                          {isOverdraft ? (
                            <span className="rounded-md bg-rose-500/10 px-2 py-1 text-xs text-rose-600">
                              透支
                            </span>
                          ) : null}
                        </div>
                      </td>
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
                      <td
                        className={`py-2 font-medium ${
                          isOverdraft ? "text-rose-600" : "text-[var(--text-primary)]"
                        }`}
                      >
                        {item.credits}
                      </td>
                      <td className="py-2 text-[var(--text-primary)]">{item.workspace_count}</td>
                      <td className="py-2 text-[var(--text-primary)]">{item.task_count}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.created_at)}</td>
                      <td className="py-2 text-[var(--text-secondary)]">{formatDate(item.last_login)}</td>
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

        <section className="route-card rounded-[1.75rem] p-5">
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
                    <SelectItem value="admin_grant">管理员发放</SelectItem>
                    <SelectItem value="admin_deduct">管理员扣减</SelectItem>
                    <SelectItem value="workflow_consume">功能扣费</SelectItem>
                    <SelectItem value="chat_token_consume">主线对话扣费</SelectItem>
                    <SelectItem value="registration_bonus">注册奖励</SelectItem>
                    <SelectItem value="refund">退款</SelectItem>
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
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={exportCreditsCsv}
                disabled={creditHistory.length === 0}
              >
                <Download className="w-4 h-4 mr-1" />
                导出 CSV
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
                    <td className="py-2 text-[var(--text-secondary)]">{formatCreditTransactionType(item.type)}</td>
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
                    <td className="py-2 text-[var(--text-secondary)]">{summarizeCreditTransaction(item)}</td>
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

        <section className="route-card rounded-[1.75rem] p-5">
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
                    <SelectItem value="credit_grant">积分发放</SelectItem>
                    <SelectItem value="credit_deduct">积分扣减</SelectItem>
                    <SelectItem value="user_role_change">角色变更</SelectItem>
                    <SelectItem value="user_status_change">状态变更</SelectItem>
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
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={exportLogsCsv}
                disabled={adminLogs.length === 0}
              >
                <Download className="w-4 h-4 mr-1" />
                导出 CSV
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
