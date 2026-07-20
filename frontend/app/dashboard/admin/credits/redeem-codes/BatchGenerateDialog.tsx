"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { batchGenerateRedeemCodes } from "@/lib/api/admin-redeem-codes";

interface Props {
  open: boolean;
  onClose: (batchId: string | null) => void;
}

export function BatchGenerateDialog({ open, onClose }: Props) {
  const [amount, setAmount] = useState("200");
  const [count, setCount] = useState("10");
  const [maxUses, setMaxUses] = useState("1");
  const [perUserLimit, setPerUserLimit] = useState("1");
  const [expiresAt, setExpiresAt] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await batchGenerateRedeemCodes({
        amount: parseInt(amount, 10),
        count: parseInt(count, 10),
        max_uses: parseInt(maxUses, 10),
        per_user_limit: parseInt(perUserLimit, 10),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        description: description.trim() || null,
      });

      // Download CSV via API
      const link = document.createElement("a");
      link.href = `/api/admin/redeem-codes/export.csv?batch_id=${encodeURIComponent(res.batch_id)}`;
      link.download = `redeem-codes-${res.batch_id}.csv`;
      link.click();

      onClose(res.batch_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>批量生成兑换码</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>每码积分</Label><Input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
            <div className="space-y-1"><Label>数量</Label><Input type="number" min={1} max={10000} value={count} onChange={(e) => setCount(e.target.value)} /></div>
            <div className="space-y-1"><Label>单码可用次数</Label><Input type="number" min={1} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} /></div>
            <div className="space-y-1"><Label>单用户上限</Label><Input type="number" min={1} value={perUserLimit} onChange={(e) => setPerUserLimit(e.target.value)} /></div>
          </div>
          <div className="space-y-1"><Label>有效期（可选）</Label><Input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} /></div>
          <div className="space-y-1"><Label>批次说明</Label><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="例如：双 11 营销" /></div>
          {error && <div className="text-sm text-[var(--wjn-error)]">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(null)} disabled={loading}>取消</Button>
          <Button onClick={handleGenerate} disabled={loading}>
            {loading && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            生成 {count} 个码并下载 CSV
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
