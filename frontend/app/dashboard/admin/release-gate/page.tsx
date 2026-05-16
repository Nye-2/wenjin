"use client";

import { useState } from "react";
import { Download, Loader2, ShieldCheck, ShieldX } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { Button } from "@/components/ui/button";
import {
  getAdminReleaseGate,
  type AdminReleaseGateReport,
  type ReleaseGateCheck,
} from "@/lib/api";

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return "-";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return dateText;
  return date.toLocaleString();
}

function getCheckStatusClass(status: ReleaseGateCheck["status"]): string {
  if (status === "passed") return "bg-emerald-500/10 text-emerald-600";
  if (status === "failed") return "bg-rose-500/10 text-rose-600";
  if (status === "pending") return "bg-amber-500/10 text-amber-600";
  return "bg-slate-500/10 text-slate-600";
}

export default function AdminReleaseGatePage() {
  const [releaseGateReport, setReleaseGateReport] = useState<AdminReleaseGateReport | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterFailed, setFilterFailed] = useState(false);

  const runReleaseGate = async (includeExtended: boolean) => {
    setError(null);
    setIsRunning(true);
    try {
      const report = await getAdminReleaseGate({ include_extended: includeExtended });
      setReleaseGateReport(report);
    } catch (err) {
      setError(
        err instanceof Error && err.message.trim() ? err.message : "发布门禁执行失败"
      );
    } finally {
      setIsRunning(false);
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

  const coreChecks = releaseGateReport?.core_gate.checks ?? [];
  const extendedChecks = releaseGateReport?.extended_gate.checks ?? [];
  const failedChecks = [...coreChecks, ...extendedChecks].filter(
    (check) => check.status === "failed" || check.status === "missing"
  );
  const isFailed = (s: string) => s === "failed" || s === "missing";
  const visibleCoreChecks = filterFailed ? coreChecks.filter((c) => isFailed(c.status)) : coreChecks;
  const visibleExtendedChecks = filterFailed ? extendedChecks.filter((c) => isFailed(c.status)) : extendedChecks;

  return (
    <>
      <AdminPageHeader
        title="发布门禁（Release Gate）"
        description="手动执行核心 / 扩展检查，输出 Go / No-Go 报告"
        actions={
          <>
            <Button
              size="sm"
              variant="outline"
              disabled={isRunning}
              onClick={() => void runReleaseGate(false)}
            >
              {isRunning ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
              运行核心门禁
            </Button>
            <Button
              size="sm"
              disabled={isRunning}
              onClick={() => void runReleaseGate(true)}
            >
              {isRunning ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
              运行核心 + 扩展检查
            </Button>
          </>
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2 mb-4">
          {error}
        </div>
      )}

      <section className="route-card rounded-[1.75rem] p-5">
        {!releaseGateReport ? (
          <div className="rounded-lg border border-dashed border-[var(--border-default)] px-3 py-4 text-sm text-[var(--text-muted)]">
            尚未执行门禁检查。点击上方按钮生成报告。
          </div>
        ) : (
          <div className="space-y-4">
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
                    onClick={() => setFilterFailed((prev) => !prev)}
                    className={`rounded px-2 py-0.5 text-[11px] font-medium transition-colors ${
                      filterFailed
                        ? "bg-rose-500/15 text-rose-600"
                        : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                    }`}
                  >
                    {filterFailed ? "仅失败/缺失" : "全部"}
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
    </>
  );
}
