import { apiClient } from "@/lib/api/client";

export interface CreditRedeemResult {
  amount: number;
  balance_after: number;
  transaction_id: string;
}

export async function redeemCreditCode(code: string): Promise<CreditRedeemResult> {
  const normalizedCode = code.trim().toUpperCase();
  const response = await apiClient.post("/credits/redeem", {
    code: normalizedCode,
  });
  return response.data;
}
