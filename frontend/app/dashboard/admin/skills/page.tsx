"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, Loader2, Plus, Upload } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  importSkillsFromSeed,
  listAdminSkills,
  toggleAdminSkill,
  type AdminSkillSummary,
} from "@/lib/api/admin-skills";

export default function SkillListPage() {
  const [items, setItems] = useState<AdminSkillSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [keyword, setKeyword] = useState("");
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    listAdminSkills()
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const handleToggle = async (item: AdminSkillSummary) => {
    await toggleAdminSkill(item.id);
    setReloadNonce((v) => v + 1);
  };

  const handleImport = async () => {
    if (
      !confirm(
        "从 seed 文件覆盖式重新灌入所有 skill？\n该操作会覆盖 DB 中的修改。"
      )
    )
      return;
    await importSkillsFromSeed();
    setReloadNonce((v) => v + 1);
  };

  const filter = keyword.trim().toLowerCase();
  const filtered = items.filter(
    (item) =>
      !filter ||
      item.id.toLowerCase().includes(filter) ||
      item.display_name.toLowerCase().includes(filter)
  );

  return (
    <>
      <AdminPageHeader
        title="Skill 管理"
        description={`共 ${items.length} 个`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleImport}>
              <Upload className="w-4 h-4 mr-1" /> 从 seed 灌入
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href="/api/admin/skills/export" download>
                <Download className="w-4 h-4 mr-1" /> 导出 zip
              </a>
            </Button>
            <Button size="sm" asChild>
              <Link href="/dashboard/admin/skills/new">
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
          <div className="flex items-center gap-2 text-[var(--text-muted)] text-sm py-6">
            <Loader2 className="w-4 h-4 animate-spin" /> 加载中
          </div>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {filtered.map((item) => (
                <tr
                  key={item.id}
                  className="border-t border-[var(--border-default)]/50"
                >
                  <td className="px-4 py-2 w-10">
                    <button
                      onClick={() => handleToggle(item)}
                      className={`inline-flex w-2.5 h-2.5 rounded-full ${
                        item.enabled ? "bg-emerald-500" : "bg-slate-400"
                      }`}
                      title={
                        item.enabled ? "已启用，点击禁用" : "已禁用，点击启用"
                      }
                    />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-[var(--text-secondary)]">
                    {item.id}
                  </td>
                  <td className="px-4 py-2 text-[var(--text-primary)]">
                    {item.display_name}
                  </td>
                  <td className="px-4 py-2 text-[var(--text-secondary)] text-xs">
                    {item.subagent_type}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      href={`/dashboard/admin/skills/${encodeURIComponent(item.id)}`}
                      className="text-sm text-[var(--accent-primary)] hover:underline"
                    >
                      编辑
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
