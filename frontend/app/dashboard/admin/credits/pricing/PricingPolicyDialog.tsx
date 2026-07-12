"use client";

import { useEffect, useState } from "react";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createPricingPolicy,
  updatePricingPolicy,
} from "@/lib/api/admin-pricing";
import type { AdminPricingPolicy } from "@/lib/api/types";

type Props = {
  open: boolean;
  policy: AdminPricingPolicy | null;
  onClose: (refresh: boolean) => void;
};

const DEFAULT_CONFIG = {
  model_usage: {
    input_weight: 0.3,
    cached_input_weight: 0.05,
    output_weight: 1,
    reasoning_weight: 1,
    credits_per_1k_weighted_tokens: 6,
    min_chat_credits: 3,
    min_mission_model_credits: 10,
    cost_guard_multiplier: 20,
    raw_cost: {
      input_usd_per_1m: 0,
      cached_input_usd_per_1m: 0,
      output_usd_per_1m: 0,
      reasoning_usd_per_1m: 0,
    },
    free_tokens: 0,
    max_overdraft_credits: 100,
  },
  global_credit: {
    credits_per_cny: 10,
    usd_to_cny: 7.3,
    target_margin_floor: 0.9,
  },
  mission: {
    estimate_min_credits: 10,
    estimate_max_credits: 100,
    max_charge_credits: 100,
  },
  sandbox: {
    operation: "run_python",
    startup_fee_credits: 1,
    minimum_billable_seconds: 60,
    max_charge_credits: 60,
    default_tier: "standard",
    tiers: {
      standard: { credits_per_minute: 1 },
    },
  },
};

export function PricingPolicyDialog({ open, policy, onClose }: Props) {
  const isEdit = policy !== null;
  const [policyKey, setPolicyKey] = useState("");
  const [policyKind, setPolicyKind] = useState("model_usage");
  const [name, setName] = useState("");
  const [configText, setConfigText] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const nextKind = policy?.policy_kind ?? "model_usage";
    setPolicyKey(policy?.policy_key ?? "");
    setPolicyKind(nextKind);
    setName(policy?.name ?? "");
    setEnabled(policy?.enabled ?? true);
    setConfigText(
      JSON.stringify(
        policy?.config ??
          DEFAULT_CONFIG[nextKind as keyof typeof DEFAULT_CONFIG],
        null,
        2,
      ),
    );
    setError(null);
  }, [open, policy]);

  const handleKindChange = (value: string) => {
    setPolicyKind(value);
    if (!isEdit) {
      setConfigText(
        JSON.stringify(
          DEFAULT_CONFIG[value as keyof typeof DEFAULT_CONFIG] ?? {},
          null,
          2,
        ),
      );
    }
  };

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const config = JSON.parse(configText) as Record<string, unknown>;
      if (isEdit) {
        await updatePricingPolicy(policy.policy_key, { name, enabled, config });
      } else {
        await createPricingPolicy({
          policy_key: policyKey,
          policy_kind: policyKind,
          name,
          enabled,
          config,
        });
      }
      onClose(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose(false);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑定价策略" : "新增定价策略"}</DialogTitle>
          <DialogDescription>
            维护 DataService 使用的积分计费配置。保存前请确认 JSON
            字段与策略类型匹配。
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="policy-key">Policy Key</Label>
            <Input
              id="policy-key"
              value={policyKey}
              disabled={isEdit}
              onChange={(event) => setPolicyKey(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="policy-kind">类型</Label>
            <Select
              value={policyKind}
              onValueChange={handleKindChange}
              disabled={isEdit}
            >
              <SelectTrigger id="policy-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global_credit">全局积分</SelectItem>
                <SelectItem value="model_usage">模型消耗</SelectItem>
                <SelectItem value="mission">研究任务</SelectItem>
                <SelectItem value="tool">工具调用</SelectItem>
                <SelectItem value="sandbox">实验环境</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="policy-name">名称</Label>
            <Input
              id="policy-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--wjn-text-secondary)]">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          启用
        </label>
        <div className="space-y-1">
          <Label htmlFor="policy-config">Config JSON</Label>
          <textarea
            id="policy-config"
            value={configText}
            onChange={(event) => setConfigText(event.target.value)}
            className="h-64 w-full rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-3 font-mono text-xs text-[var(--wjn-text)] outline-none focus:border-[var(--wjn-navy)]"
          />
        </div>
        {error && <div className="text-sm text-rose-600">{error}</div>}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onClose(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
