"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BatchGenerateDialog } from "./BatchGenerateDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  disableRedeemCode, listRedeemCodes, type RedeemCode,
} from "@/lib/api/admin-redeem-codes";

function formatDate(s: string | null) {
  if (!s) return "-";
  return new Date(s).toLocaleString();
}

export default function RedeemCodesPage() {
  const [codes, setCodes] = useState<RedeemCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [batchId, setBatchId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    setLoading(true);
    listRedeemCodes({
      batch_id: batchId || undefined, keyword: keyword || undefined,
      page, page_size: 50,
    })
      .then((res) => setCodes(res.items))
      .finally(() => setLoading(false));
  }, [batchId, keyword, page, reloadNonce]);

  const handleDisable = async (code: RedeemCode) => {
    if (!confirm(`下线兑换码 ${code.code}？`)) return;
    await disableRedeemCode(code.id);
    setReloadNonce((v) => v + 1);
  };

  return (
    <>
      <AdminPageHeader
        title="兑换码"
        actions={
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> 批量生成
          </Button>
        }
      />

      <div className="route-card rounded-2xl p-4 mb-4 flex flex-wrap gap-2">
        <Input placeholder="批次 ID" value={batchId} onChange={(e) => { setBatchId(e.target.value); setPage(1); }} className="max-w-xs" />
        <Input placeholder="关键词" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(1); }} className="max-w-xs" />
      </div>

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--border-default)]">
              <th className="px-4 py-3 w-12"></th>
              <th className="px-4 py-3">兑换码</th>
              <th className="px-4 py-3 text-right">积分</th>
              <th className="px-4 py-3">使用情况</th>
              <th className="px-4 py-3">到期时间</th>
              <th className="px-4 py-3">批次</th>
              <th className="px-4 py-3 w-20 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {codes.map((c) => (
              <tr key={c.id} className="border-t border-[var(--border-default)]/50">
                <td className="px-4 py-3">
                  <span className={`inline-flex w-2.5 h-2.5 rounded-full ${c.enabled ? "bg-emerald-500" : "bg-slate-400"}`} />
                </td>
                <td className="px-4 py-3 font-mono text-xs">{c.code}</td>
                <td className="px-4 py-3 text-right font-medium">+{c.amount}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{c.use_count}/{c.max_uses}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{formatDate(c.expires_at)}</td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--text-muted)]">{c.batch_id?.slice(0, 8) ?? "-"}</td>
                <td className="px-4 py-3 text-right">
                  {c.enabled && <button onClick={() => handleDisable(c)} className="text-rose-600 hover:underline text-sm">下线</button>}
                </td>
              </tr>
            ))}
            {!loading && codes.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-[var(--text-muted)]">暂无兑换码</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex justify-between items-center">
        <span className="text-xs text-[var(--text-muted)]">第 {page} 页</span>
        <div className="space-x-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
          <Button variant="outline" size="sm" disabled={codes.length < 50} onClick={() => setPage(page + 1)}>下一页</Button>
        </div>
      </div>

      <BatchGenerateDialog
        open={dialogOpen}
        onClose={(batch) => {
          setDialogOpen(false);
          if (batch) setReloadNonce((v) => v + 1);
        }}
      />
    </>
  );
}
