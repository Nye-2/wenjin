"use client";

import { useEffect, useState } from "react";
import { Calculator, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listPricingPolicies, simulatePricing } from "@/lib/api/admin-pricing";
import type { AdminPricingPolicy, AdminPricingSimulationResult } from "@/lib/api/types";

const DEFAULT_GLOBAL_POLICY = { credits_per_cny: 10, usd_to_cny: 7.3 };
const DEFAULT_MODEL_USAGE_POLICY = {
  input_weight: 0.3,
  output_weight: 1,
  credits_per_1k_weighted_tokens: 6,
  min_chat_credits: 3,
  min_feature_model_credits: 10,
  cost_guard_multiplier: 20,
};

export function PricingSimulator() {
  const [promptTokens, setPromptTokens] = useState("1000");
  const [completionTokens, setCompletionTokens] = useState("500");
  const [result, setResult] = useState<AdminPricingSimulationResult | null>(null);
  const [globalPolicy, setGlobalPolicy] = useState<Record<string, unknown>>(DEFAULT_GLOBAL_POLICY);
  const [modelUsagePolicy, setModelUsagePolicy] = useState<Record<string, unknown>>(DEFAULT_MODEL_USAGE_POLICY);
  const [policySource, setPolicySource] = useState("默认模板");
  const [loading, setLoading] = useState(false);
  const [policiesLoading, setPoliciesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPoliciesLoading(true);
    Promise.all([
      listPricingPolicies({ policy_kind: "global_credit", enabled_only: true }),
      listPricingPolicies({ policy_kind: "model_usage", enabled_only: true }),
    ])
      .then(([globalResponse, modelResponse]) => {
        if (cancelled) return;
        const activeGlobal = firstPolicyConfig(globalResponse.items, "global_credit");
        const activeModel = firstPolicyConfig(modelResponse.items, "model_usage");
        setGlobalPolicy(activeGlobal ?? DEFAULT_GLOBAL_POLICY);
        setModelUsagePolicy(activeModel ?? DEFAULT_MODEL_USAGE_POLICY);
        setPolicySource(activeGlobal && activeModel ? "当前启用策略" : "默认模板");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "定价策略加载失败");
          setGlobalPolicy(DEFAULT_GLOBAL_POLICY);
          setModelUsagePolicy(DEFAULT_MODEL_USAGE_POLICY);
          setPolicySource("默认模板");
        }
      })
      .finally(() => {
        if (!cancelled) setPoliciesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSimulate = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await simulatePricing({
        policy_kind: "model_usage",
        surface: "chat",
        prompt_tokens: parseInt(promptTokens, 10) || 0,
        completion_tokens: parseInt(completionTokens, 10) || 0,
        global_policy: globalPolicy,
        model_usage_policy: modelUsagePolicy,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "估算失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="route-card rounded-2xl p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">定价模拟</h2>
          <p className="text-sm text-[var(--text-muted)]">按{policySource}估算积分与毛利。</p>
        </div>
        <Button size="sm" onClick={handleSimulate} disabled={loading || policiesLoading}>
          {loading || policiesLoading ? (
            <Loader2 className="w-4 h-4 mr-1 animate-spin" />
          ) : (
            <Calculator className="w-4 h-4 mr-1" />
          )}
          估算积分
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="prompt-tokens">Prompt tokens</Label>
          <Input
            id="prompt-tokens"
            type="number"
            value={promptTokens}
            onChange={(event) => setPromptTokens(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="completion-tokens">Completion tokens</Label>
          <Input
            id="completion-tokens"
            type="number"
            value={completionTokens}
            onChange={(event) => setCompletionTokens(event.target.value)}
          />
        </div>
        <div className="rounded-lg border border-[var(--border-default)] px-3 py-2">
          <div className="text-xs text-[var(--text-muted)]">应收</div>
          <div className="text-lg font-semibold text-[var(--text-primary)]">
            {result ? `${result.charge_credits} credits` : "-"}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--border-default)] px-3 py-2">
          <div className="text-xs text-[var(--text-muted)]">毛利</div>
          <div className="text-lg font-semibold text-[var(--text-primary)]">
            {result ? `毛利 ${formatNumber(result.margin_cny ?? 0)} CNY` : "-"}
          </div>
        </div>
      </div>
      {error && <div className="mt-3 text-sm text-rose-600">{error}</div>}
      {result?.breakdown && (
        <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-secondary)]">
          {JSON.stringify(result.breakdown, null, 2)}
        </pre>
      )}
    </section>
  );
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function firstPolicyConfig(
  policies: AdminPricingPolicy[],
  kind: string,
): Record<string, unknown> | null {
  return policies.find((policy) => policy.enabled && policy.policy_kind === kind)?.config ?? null;
}
