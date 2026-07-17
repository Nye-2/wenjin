import { apiClient } from "@/lib/api/client";
import type {
  AdminDashboardData,
  AdminLogItem,
  AdminReleaseGateReport,
  AdminUserItem,
  CreditTransactionItem,
  UserDashboardData,
} from "@/lib/api/types";

export async function getMyDashboard(): Promise<UserDashboardData> {
  const response = await apiClient.get("/dashboard/me");
  return response.data;
}

export async function getMyCreditHistory(params?: {
  page?: number;
  page_size?: number;
  transaction_type?: string;
}): Promise<{
  transactions: CreditTransactionItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get("/dashboard/me/credits/history", {
    params,
  });
  return response.data;
}

export async function getAdminDashboard(): Promise<AdminDashboardData> {
  const response = await apiClient.get("/dashboard/admin");
  return response.data;
}

export async function getAdminReleaseGate(params?: {
  include_extended?: boolean;
}): Promise<AdminReleaseGateReport> {
  const response = await apiClient.get("/dashboard/admin/release-gate", {
    params,
  });
  return response.data;
}

export async function listAdminUsers(params?: {
  page?: number;
  page_size?: number;
  keyword?: string;
  is_active?: boolean;
  role?: "user" | "admin";
}): Promise<{
  users: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get("/dashboard/admin/users", { params });
  return response.data;
}

export async function updateAdminUserStatus(
  userId: string,
  isActive: boolean
): Promise<{ success: boolean; user: AdminUserItem }> {
  const response = await apiClient.post(`/dashboard/admin/users/${userId}/status`, {
    is_active: isActive,
  });
  return response.data;
}

export async function updateAdminUserRole(
  userId: string,
  role: "user" | "admin"
): Promise<{ success: boolean; user: AdminUserItem }> {
  const response = await apiClient.post(`/dashboard/admin/users/${userId}/role`, {
    role,
  });
  return response.data;
}

export async function adminGrantCredits(data: {
  user_id: string;
  amount: number;
  description?: string;
}): Promise<{
  success: boolean;
  transaction: {
    id: string;
    amount: number;
    balance_after: number;
  };
}> {
  const response = await apiClient.post("/dashboard/admin/credits/grant", data);
  return response.data;
}

export async function adminDeductCredits(data: {
  user_id: string;
  amount: number;
  description?: string;
}): Promise<{
  success: boolean;
  transaction: {
    id: string;
    amount: number;
    balance_after: number;
  };
}> {
  const response = await apiClient.post("/dashboard/admin/credits/deduct", data);
  return response.data;
}

export async function getAdminCreditHistory(params?: {
  page?: number;
  page_size?: number;
  user_id?: string;
  transaction_type?: string;
}): Promise<{
  transactions: CreditTransactionItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get("/dashboard/admin/credits/history", {
    params,
  });
  return response.data;
}

export async function getAdminLogs(params?: {
  page?: number;
  page_size?: number;
  action?: string;
  target_user_id?: string;
}): Promise<{
  logs: AdminLogItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get("/dashboard/admin/logs", { params });
  return response.data;
}
