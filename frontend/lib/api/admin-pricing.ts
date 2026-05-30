import { apiClient } from "@/lib/api/client";
import type {
  AdminPricingPolicy,
  AdminPricingSimulationRequest,
  AdminPricingSimulationResult,
} from "@/lib/api/types";

export type PricingPolicyCreatePayload = {
  policy_key: string;
  policy_kind: string;
  name: string;
  config: Record<string, unknown>;
  enabled?: boolean;
};

export type PricingPolicyUpdatePayload = Partial<Omit<PricingPolicyCreatePayload, "policy_key" | "policy_kind">>;

export async function listPricingPolicies(params?: {
  policy_kind?: string;
  enabled_only?: boolean;
}): Promise<{ items: AdminPricingPolicy[]; total: number }> {
  const response = await apiClient.get("/admin/pricing-policies", { params });
  return response.data;
}

export async function createPricingPolicy(
  payload: PricingPolicyCreatePayload,
): Promise<AdminPricingPolicy> {
  const response = await apiClient.post("/admin/pricing-policies", payload);
  return response.data;
}

export async function updatePricingPolicy(
  policyIdOrKey: string,
  payload: PricingPolicyUpdatePayload,
): Promise<AdminPricingPolicy | null> {
  const response = await apiClient.patch(
    `/admin/pricing-policies/${encodeURIComponent(policyIdOrKey)}`,
    payload,
  );
  return response.data;
}

export async function disablePricingPolicy(policyIdOrKey: string): Promise<AdminPricingPolicy | null> {
  const response = await apiClient.post(
    `/admin/pricing-policies/${encodeURIComponent(policyIdOrKey)}/disable`,
  );
  return response.data;
}

export async function simulatePricing(
  payload: AdminPricingSimulationRequest,
): Promise<AdminPricingSimulationResult> {
  const response = await apiClient.post("/admin/pricing/simulate", payload);
  return response.data;
}
