"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  createCreditRule, updateCreditRule, type CreditGrantRule, type RuleType,
} from "@/lib/api/admin-credit-rules";

interface Props {
  open: boolean;
  rule: CreditGrantRule | null;
  onClose: (refresh: boolean) => void;
}

export function CreditRuleDialog({ open, rule, onClose }: Props) {
  const isEdit = rule !== null;
  const [name, setName] = useState(rule?.name ?? "");
  const [ruleType, setRuleType] = useState<RuleType>(rule?.rule_type ?? "registration_bonus");
  const [amount, setAmount] = useState(String(rule?.amount ?? 100));
  const [description, setDescription] = useState(rule?.description ?? "");
  const [trigger, setTrigger] = useState<string>(
    (rule?.config?.trigger as string) ?? (ruleType === "referral_referrer" ? "on_first_task" : "on_signup")
  );
  const [cron, setCron] = useState((rule?.config?.cron as string) ?? "0 0 * * 1");
  const [activeWithinDays, setActiveWithinDays] = useState(
    String((rule?.config?.target_filter as Record<string, unknown>)?.active_within_days ?? 30)
  );
  const [role, setRole] = useState(
    ((rule?.config?.target_filter as Record<string, unknown>)?.role as string) ?? "user"
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const buildConfig = (): Record<string, any> => {
    switch (ruleType) {
      case "registration_bonus":
        return {};
      case "referral_referrer":
        return { trigger };
      case "referral_referred":
        return { trigger: "on_signup" };
      case "periodic":
        return {
          cron,
          target_filter: {
            active_within_days: parseInt(activeWithinDays, 10) || null,
            role: role || null,
          },
        };
    }
  };

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      const payload = { name, amount: parseInt(amount, 10), config: buildConfig(), description: description || undefined };
      if (isEdit) {
        await updateCreditRule(rule!.id, payload);
      } else {
        await createCreditRule({ ...payload, rule_type: ruleType });
      }
      onClose(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(false); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑规则" : "新建规则"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>规则名</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>类型</Label>
            <Select value={ruleType} onValueChange={(v) => setRuleType(v as RuleType)} disabled={isEdit}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="registration_bonus">注册奖励</SelectItem>
                <SelectItem value="referral_referrer">邀请者奖励</SelectItem>
                <SelectItem value="referral_referred">被邀请者奖励</SelectItem>
                <SelectItem value="periodic">周期发放</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>积分数量</Label>
            <Input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>

          {ruleType === "referral_referrer" && (
            <div className="space-y-1">
              <Label>触发时机</Label>
              <Select value={trigger} onValueChange={setTrigger}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="on_signup">被邀请者注册时</SelectItem>
                  <SelectItem value="on_first_task">被邀请者首次完成任务时（推荐）</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {ruleType === "periodic" && (
            <>
              <div className="space-y-1">
                <Label>Cron 表达式</Label>
                <Input value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 0 * * 1" />
                <p className="text-xs text-[var(--text-muted)]">每周一 00:00：<code>0 0 * * 1</code></p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label>活跃天数内</Label>
                  <Input type="number" min={1} value={activeWithinDays} onChange={(e) => setActiveWithinDays(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>角色</Label>
                  <Select value={role} onValueChange={setRole}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">普通用户</SelectItem>
                      <SelectItem value="admin">管理员</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}

          <div className="space-y-1">
            <Label>说明（可选）</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>

          {error && <div className="text-sm text-rose-600">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={loading}>取消</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {isEdit ? "保存" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
