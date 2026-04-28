import { apiClient } from "@/lib/api/client";
import type {
  ComputeProjection,
  ComputeSession,
  ComputeSessionListResponse,
} from "@/lib/api/types";

export async function getWorkspaceComputeSessions(
  workspaceId: string,
  limit: number = 20
): Promise<ComputeSessionListResponse> {
  const response = await apiClient.get(
    `/workspaces/${encodeURIComponent(workspaceId)}/compute/sessions`,
    { params: { limit } }
  );
  return response.data;
}

export async function getComputeSession(
  computeSessionId: string
): Promise<ComputeSession> {
  const response = await apiClient.get(
    `/compute/sessions/${encodeURIComponent(computeSessionId)}`
  );
  return response.data;
}

export async function getComputeProjection(
  computeSessionId: string
): Promise<ComputeProjection> {
  const response = await apiClient.get(
    `/compute/sessions/${encodeURIComponent(computeSessionId)}/projection`
  );
  return response.data;
}

