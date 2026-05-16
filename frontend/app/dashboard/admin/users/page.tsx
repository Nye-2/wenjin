"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { CreditAdjustDialog } from "../components/CreditAdjustDialog";
import { Button } from "@/components/ui/button";
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
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
  type AdminUserItem,
} from "@/lib/api";

type UserRoleFilter = "all" | "user" | "admin";
type UserStatusFilter = "all" | "active" | "inactive";
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

  const blob = new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersHasMore, setUsersHasMore] = useState(false);
  const [usersPage, setUsersPage] = useState(1);
  const [usersPageSize, setUsersPageSize] = useState<number>(20);
  const [userKeywordInput, setUserKeywordInput] = useState("");
  const [userKeywordQuery, setUserKeywordQuery] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState<UserRoleFilter>("all");
  const [userStatusFilter, setUserStatusFilter] = useState<UserStatusFilter>("all");
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoadingUserId, setActionLoadingUserId] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [creditDialogMode, setCreditDialogMode] = useState<CreditDialogMode | null>(null);
  const [creditDialogUser, setCreditDialogUser] = useState<AdminUserItem | null>(null);

  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const loadUsers = async () => {
      if (!hasLoadedOnceRef.current) {
        setIsLoading(true);
      }
      setError(null);

      const usersRole = userRoleFilter === "all" ? undefined : userRoleFilter;
      const usersIsActive =
        userStatusFilter === "all" ? undefined : userStatusFilter === "active";

      try {
        const usersRes = await listAdminUsers({
          page: usersPage,
          page_size: usersPageSize,
          keyword: userKeywordQuery || undefined,
          is_active: usersIsActive,
          role: usersRole,
        });
        if (!cancelled) {
          setUsers(usersRes.users);
          setUsersTotal(usersRes.total);
          setUsersHasMore(usersRes.has_more);
        }
      } catch (err) {
        if (!cancelled) {
          setError(parseErrorMessage(err, "加载用户列表失败"));
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          hasLoadedOnceRef.current = true;
        }
      }
    };

    void loadUsers();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce, usersPage, usersPageSize, userKeywordQuery, userRoleFilter, userStatusFilter]);

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

  const usersStart = usersTotal === 0 ? 0 : (usersPage - 1) * usersPageSize + 1;
  const usersEnd = Math.min(usersTotal, usersPage * usersPageSize);

  return (
    <>
      <AdminPageHeader
        title="用户管理"
        description={`显示 ${usersStart}-${usersEnd} / 共 ${usersTotal}`}
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
        actions={
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
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2 mb-4">
          {error}
        </div>
      )}

      <section className="route-card rounded-[1.75rem] p-5">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-4">
          <div />
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
                          onClick={() => {
                            setCreditDialogMode("grant");
                            setCreditDialogUser(item);
                          }}
                          className="px-2 py-1 rounded-md text-xs bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 disabled:opacity-60"
                        >
                          发放
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => {
                            setCreditDialogMode("deduct");
                            setCreditDialogUser(item);
                          }}
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
          {isLoading && (
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
                disabled={usersPage <= 1 || isLoading}
                onClick={() => setUsersPage((value) => Math.max(1, value - 1))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!usersHasMore || isLoading}
                onClick={() => setUsersPage((value) => value + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        </div>
      </section>

      <CreditAdjustDialog
        mode={creditDialogMode}
        user={creditDialogUser}
        onClose={(refresh) => {
          setCreditDialogMode(null);
          setCreditDialogUser(null);
          if (refresh) setReloadNonce((v) => v + 1);
        }}
      />
    </>
  );
}
