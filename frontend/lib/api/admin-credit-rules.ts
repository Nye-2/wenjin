import { apiClient } from "@/lib/api/client";

export type RuleType = "registration_bonus" | "referral_referrer" | "referral_referred" | "periodic";

export interface CreditGrantRule {
  id: string;
  name: string;
  rule_type: RuleType;
  enabled: boolean;
  amount: number;
  description: string | null;
  config: Record<string, unknown>;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export async function listCreditRules(): Promise<{ items: CreditGrantRule[]; total: number }> {
  const response = await apiClient.get("/admin/credit-rules");
  return response.data;
}

export async function createCreditRule(payload: {
  name: string;
  rule_type: RuleType;
  amount: number;
  config: Record<string, unknown>;
  description?: string;
}): Promise<CreditGrantRule> {
  const response = await apiClient.post("/admin/credit-rules", payload);
  return response.data;
}

export async function updateCreditRule(
  id: string,
  payload: { name: string; amount: number; config: Record<string, unknown>; description?: string }
): Promise<CreditGrantRule> {
  const response = await apiClient.put(`/admin/credit-rules/${id}`, payload);
  return response.data;
}

export async function toggleCreditRule(id: string): Promise<CreditGrantRule> {
  const response = await apiClient.post(`/admin/credit-rules/${id}/toggle`);
  return response.data;
}

export async function deleteCreditRule(id: string): Promise<void> {
  await apiClient.delete(`/admin/credit-rules/${id}`);
}
