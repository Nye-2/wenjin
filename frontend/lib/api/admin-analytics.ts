import { apiClient } from "@/lib/api/client";

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface UserGrowthKPIs {
  total_users: number;
  new_in_range: number;
  dau: number;
  wau: number;
}

export interface UserGrowthTimePoint {
  date: string;
  signups: number;
}

export interface UserGrowthResponse {
  kpis: UserGrowthKPIs;
  time_series: UserGrowthTimePoint[];
}

export interface MissionKPIs {
  total: number;
  success: number;
  failed: number;
  success_rate: number;
}

export interface MissionTimePoint {
  date: string;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
}

export interface WorkspaceTypeCount {
  type: string;
  count: number;
}

export interface MissionStatsResponse {
  kpis: MissionKPIs;
  time_series: MissionTimePoint[];
  by_workspace_type: WorkspaceTypeCount[];
}

export interface CreditKPIs {
  total_issued: number;
  total_spent: number;
  current_pool: number;
}

export interface CreditTimePoint {
  date: string;
  inflow: number;
  outflow: number;
  by_type: Record<string, number>;
}

export interface CreditConsumptionResponse {
  kpis: CreditKPIs;
  credit_series: CreditTimePoint[];
}

export interface WorkspaceAdoptionResponse {
  by_type: WorkspaceTypeCount[];
  total_workspaces: number;
  users_with_workspaces: number;
  adoption_rate: number;
}

// ------------------------------------------------------------------
// API functions
// ------------------------------------------------------------------

export async function getUserGrowth(params?: {
  range?: string;
  granularity?: "day" | "week";
  cache_bust?: boolean;
}): Promise<UserGrowthResponse> {
  const response = await apiClient.get(
    "/dashboard/admin/analytics/user-growth",
    { params }
  );
  return response.data;
}

export async function getMissionStats(params?: {
  range?: string;
  granularity?: "day" | "week";
  cache_bust?: boolean;
}): Promise<MissionStatsResponse> {
  const response = await apiClient.get(
    "/dashboard/admin/analytics/mission-stats",
    { params }
  );
  return response.data;
}

export async function getCreditConsumption(params?: {
  range?: string;
  granularity?: "day" | "week";
  cache_bust?: boolean;
}): Promise<CreditConsumptionResponse> {
  const response = await apiClient.get(
    "/dashboard/admin/analytics/credit-consumption",
    { params }
  );
  return response.data;
}

export async function getWorkspaceAdoption(params?: {
  cache_bust?: boolean;
}): Promise<WorkspaceAdoptionResponse> {
  const response = await apiClient.get(
    "/dashboard/admin/analytics/workspace-adoption",
    { params }
  );
  return response.data;
}
