import { apiClient } from "@/lib/api/client";

export interface RedeemCode {
  id: string;
  code: string;
  amount: number;
  max_uses: number;
  use_count: number;
  per_user_limit: number;
  expires_at: string | null;
  enabled: boolean;
  batch_id: string | null;
  description: string | null;
  created_at: string;
}

export async function listRedeemCodes(params: {
  batch_id?: string; enabled?: boolean; keyword?: string; page?: number; page_size?: number;
}): Promise<{ items: RedeemCode[]; page: number }> {
  const response = await apiClient.get("/admin/redeem-codes", { params });
  return response.data;
}

export async function batchGenerateRedeemCodes(payload: {
  amount: number; count: number; max_uses: number; per_user_limit: number;
  expires_at: string | null; description: string | null;
}): Promise<{ batch_id: string; items: RedeemCode[] }> {
  const response = await apiClient.post("/admin/redeem-codes/batch", payload);
  return response.data;
}

export async function disableRedeemCode(id: string): Promise<RedeemCode> {
  const response = await apiClient.post(`/admin/redeem-codes/${id}/disable`);
  return response.data;
}
