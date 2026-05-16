"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

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
  adminDeductCredits,
  adminGrantCredits,
  type AdminUserItem,
} from "@/lib/api";

type Mode = "grant" | "deduct";

interface Props {
  mode: Mode | null;
  user: AdminUserItem | null;
  onClose: (refresh: boolean) => void;
}

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const responseData = (error as { response?: { data?: unknown } }).response?.data;
    if (responseData && typeof responseData === "object" && "detail" in responseData) {
      const detail = (responseData as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export function CreditAdjustDialog({ mode, user, onClose }: Props) {
  const [amount, setAmount] = useState("100");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!mode || !user) return null;

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || !Number.isInteger(value) || value <= 0) {
      setError("积分数量必须是正整数");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const finalDescription =
        description.trim() || (mode === "grant" ? "管理员发放积分" : "管理员扣除积分");
      if (mode === "grant") {
        await adminGrantCredits({ user_id: user.id, amount: value, description: finalDescription });
      } else {
        await adminDeductCredits({ user_id: user.id, amount: value, description: finalDescription });
      }
      onClose(true);
    } catch (err) {
      setError(parseErrorMessage(err, "积分操作失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose(false);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "grant" ? "发放积分" : "扣除积分"}</DialogTitle>
          <DialogDescription>目标用户：{user.email}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="credit-amount">积分数量（正整数）</Label>
            <Input
              id="credit-amount"
              type="number"
              min={1}
              step={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={loading}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="credit-description">原因说明</Label>
            <Input
              id="credit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="请输入原因"
              maxLength={500}
              disabled={loading}
            />
          </div>
          {error && (
            <div className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg p-2">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {mode === "grant" ? "确认发放" : "确认扣除"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
