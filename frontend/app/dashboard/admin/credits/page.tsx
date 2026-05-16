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
  formatCreditTransactionType,
  summarizeCreditTransaction,
} from "@/lib/credit-display";
import {
  getAdminCreditHistory,
  type CreditTransactionItem,
} from "@/lib/api";

type CreditTypeFilter =
  | "all"
  | "admin_grant"
  | "admin_deduct"
  | "workflow_consume"
  | "thread_token_consume"
  | "registration_bonus"
  | "refund";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
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

export default function AdminCreditsPage() {
  const [creditHistory, setCreditHistory] = useState<CreditTransactionItem[]>([]);
  const [creditTotal, setCreditTotal] = useState(0);
  const [creditHasMore, setCreditHasMore] = useState(false);
  const [creditPage, setCreditPage] = useState(1);
  const [creditPageSize, setCreditPageSize] = useState<number>(10);
  const [creditTypeFilter, setCreditTypeFilter] = useState<CreditTypeFilter>("all");
  const [creditUserIdInput, setCreditUserIdInput] = useState("");
  const [creditUserIdQuery, setCreditUserIdQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadCredits = async () => {
      setIsLoading(true);
      setError(null);

      const creditType = creditTypeFilter === "all" ? undefined : creditTypeFilter;

      try {
        const creditsRes = await getAdminCreditHistory({
          page: creditPage,
          page_size: creditPageSize,
          user_id: creditUserIdQuery || undefined,
          transaction_type: creditType,
        });
        if (!cancelled) {
          setCreditHistory(creditsRes.transactions);
          setCreditTotal(creditsRes.total);
          setCreditHasMore(creditsRes.has_more);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error && err.message.trim() ? err.message : "加载积分流水失败"
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadCredits();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce, creditPage, creditPageSize, creditTypeFilter, creditUserIdQuery]);

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

  const creditsStart = creditTotal === 0 ? 0 : (creditPage - 1) * creditPageSize + 1;
  const creditsEnd = Math.min(creditTotal, creditPage * creditPageSize);

  return (
    <>
      <AdminPageHeader
        title="积分流水"
        description={`显示 ${creditsStart}-${creditsEnd} / 共 ${creditTotal}`}
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
        actions={
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
                  <SelectItem value="thread_token_consume">主线对话扣费</SelectItem>
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
          {isLoading && (
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
                disabled={creditPage <= 1 || isLoading}
                onClick={() => setCreditPage((value) => Math.max(1, value - 1))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!creditHasMore || isLoading}
                onClick={() => setCreditPage((value) => value + 1)}
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
