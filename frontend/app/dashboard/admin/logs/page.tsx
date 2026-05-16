"use client";

import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
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
  getAdminLogs,
  type AdminLogItem,
} from "@/lib/api";

type LogActionFilter =
  | "all"
  | "credit_grant"
  | "credit_deduct"
  | "user_role_change"
  | "user_status_change";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
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

  const blob = new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AdminLogsPage() {
  const [adminLogs, setAdminLogs] = useState<AdminLogItem[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logsHasMore, setLogsHasMore] = useState(false);
  const [logsPage, setLogsPage] = useState(1);
  const [logsPageSize, setLogsPageSize] = useState<number>(10);
  const [logActionFilter, setLogActionFilter] = useState<LogActionFilter>("all");
  const [logTargetUserIdInput, setLogTargetUserIdInput] = useState("");
  const [logTargetUserIdQuery, setLogTargetUserIdQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadLogs = async () => {
      setIsLoading(true);
      setError(null);

      const logAction = logActionFilter === "all" ? undefined : logActionFilter;

      try {
        const logsRes = await getAdminLogs({
          page: logsPage,
          page_size: logsPageSize,
          action: logAction,
          target_user_id: logTargetUserIdQuery || undefined,
        });
        if (!cancelled) {
          setAdminLogs(logsRes.logs);
          setLogsTotal(logsRes.total);
          setLogsHasMore(logsRes.has_more);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error && err.message.trim() ? err.message : "加载管理员日志失败"
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadLogs();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce, logsPage, logsPageSize, logActionFilter, logTargetUserIdQuery]);

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

  const logsStart = logsTotal === 0 ? 0 : (logsPage - 1) * logsPageSize + 1;
  const logsEnd = Math.min(logsTotal, logsPage * logsPageSize);

  return (
    <>
      <AdminPageHeader
        title="管理员日志"
        description={`显示 ${logsStart}-${logsEnd} / 共 ${logsTotal}`}
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
        actions={
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
          {isLoading && (
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
                disabled={logsPage <= 1 || isLoading}
                onClick={() => setLogsPage((value) => Math.max(1, value - 1))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!logsHasMore || isLoading}
                onClick={() => setLogsPage((value) => value + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
