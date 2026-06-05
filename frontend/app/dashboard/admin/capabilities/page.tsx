"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, Loader2, Plus, Upload } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  importCapabilitiesFromSeed,
  listAdminCapabilities,
  toggleAdminCapability,
  type AdminCapabilitySummary,
} from "@/lib/api/admin-capabilities";

const WS_LABEL: Record<string, string> = {
  thesis: "论文",
  sci: "SCI",
  proposal: "开题",
  software_copyright: "软著",
  patent: "专利",
};

export default function CapabilityListPage() {
  const [groups, setGroups] = useState<
    Record<string, AdminCapabilitySummary[]>
  >({});
  const [isLoading, setIsLoading] = useState(true);
  const [keyword, setKeyword] = useState("");
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setIsLoading(true);
      }
    });
    listAdminCapabilities()
      .then((res) => {
        if (!cancelled) setGroups(res.groups);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const handleToggle = async (item: AdminCapabilitySummary) => {
    await toggleAdminCapability(item.id, item.workspace_type);
    setReloadNonce((v) => v + 1);
  };

  const handleImport = async () => {
    if (
      !confirm(
        "从 seed 文件覆盖式重新灌入所有 capability？\n该操作会覆盖 DB 中的修改。"
      )
    )
      return;
    await importCapabilitiesFromSeed();
    setReloadNonce((v) => v + 1);
  };

  const filter = keyword.trim().toLowerCase();
  const filterMatch = (item: AdminCapabilitySummary) =>
    !filter ||
    item.id.toLowerCase().includes(filter) ||
    item.display_name.toLowerCase().includes(filter);

  return (
    <>
      <AdminPageHeader
        title="Capability 管理"
        description={`共 ${Object.values(groups).flat().length} 个`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleImport}>
              <Upload className="w-4 h-4 mr-1" /> 从 seed 灌入
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href="/api/admin/capabilities/export" download>
                <Download className="w-4 h-4 mr-1" /> 导出 zip
              </a>
            </Button>
            <Button size="sm" asChild>
              <Link href="/dashboard/admin/capabilities/new">
                <Plus className="w-4 h-4 mr-1" />
                新建
              </Link>
            </Button>
          </>
        }
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
      />

      <div className="route-card rounded-2xl p-5">
        <Input
          placeholder="搜索 id 或 display_name"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="max-w-md mb-4"
        />

        {isLoading ? (
          <div className="flex items-center gap-2 text-[var(--wjn-text-muted)] text-sm py-6">
            <Loader2 className="w-4 h-4 animate-spin" /> 加载中
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groups).map(([wsType, items]) => {
              const filtered = items.filter(filterMatch);
              if (filtered.length === 0) return null;
              return (
                <details
                  key={wsType}
                  open
                  className="rounded-xl border border-[var(--wjn-line)]"
                >
                  <summary className="cursor-pointer list-none px-4 py-3 font-medium text-[var(--wjn-text)]">
                    {WS_LABEL[wsType] ?? wsType} · {wsType} · {filtered.length}{" "}
                    个
                  </summary>
                  <table className="w-full text-sm">
                    <tbody>
                      {filtered.map((item) => (
                        <tr
                          key={item.id}
                          className="border-t border-[var(--wjn-line)]/50"
                        >
                          <td className="px-4 py-2 w-10">
                            <button
                              onClick={() => handleToggle(item)}
                              className={`inline-flex w-2.5 h-2.5 rounded-full ${
                                item.enabled ? "bg-emerald-500" : "bg-slate-400"
                              }`}
                              title={
                                item.enabled
                                  ? "已启用，点击禁用"
                                  : "已禁用，点击启用"
                              }
                            />
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-[var(--wjn-text-secondary)]">
                            {item.id}
                          </td>
                          <td className="px-4 py-2 text-[var(--wjn-text)]">
                            {item.display_name}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <Link
                              href={`/dashboard/admin/capabilities/${encodeURIComponent(item.id)}?workspace_type=${item.workspace_type}`}
                              className="text-sm text-[var(--wjn-navy)] hover:underline"
                            >
                              编辑
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
