import { apiClient } from "@/lib/api/client";
import type {
  RunCancelAction,
  RunRequest,
  RunResponse,
  RunWaitResponse,
} from "@/lib/api/types";

export async function createThreadRun(
  threadId: string,
  data: RunRequest
): Promise<RunResponse> {
  const response = await apiClient.post(
    `/threads/${encodeURIComponent(threadId)}/runs`,
    data
  );
  return response.data;
}

export async function waitThreadRun(
  threadId: string,
  data: RunRequest
): Promise<RunWaitResponse> {
  const response = await apiClient.post(
    `/threads/${encodeURIComponent(threadId)}/runs/wait`,
    data
  );
  return response.data;
}

export async function getThreadRun(
  threadId: string,
  runId: string
): Promise<RunResponse> {
  const response = await apiClient.get(
    `/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}`
  );
  return response.data;
}

export async function cancelThreadRun(
  threadId: string,
  runId: string,
  options: {
    action?: RunCancelAction;
    wait?: boolean;
  } = {}
): Promise<void> {
  const query = new URLSearchParams();
  if (options.action) {
    query.set("action", options.action);
  }
  if (typeof options.wait === "boolean") {
    query.set("wait", options.wait ? "true" : "false");
  }
  const suffix = query.toString();
  await apiClient.post(
    `/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/cancel${suffix ? `?${suffix}` : ""}`
  );
}

export async function getRun(runId: string): Promise<RunResponse> {
  const response = await apiClient.get(`/runs/${encodeURIComponent(runId)}`);
  return response.data;
}

export async function cancelRun(
  runId: string,
  options: {
    action?: RunCancelAction;
    wait?: boolean;
  } = {}
): Promise<void> {
  const query = new URLSearchParams();
  if (options.action) {
    query.set("action", options.action);
  }
  if (typeof options.wait === "boolean") {
    query.set("wait", options.wait ? "true" : "false");
  }
  const suffix = query.toString();
  await apiClient.post(
    `/runs/${encodeURIComponent(runId)}/cancel${suffix ? `?${suffix}` : ""}`
  );
}

export async function waitRun(data: RunRequest): Promise<RunWaitResponse> {
  const response = await apiClient.post("/runs/wait", data);
  return response.data;
}

export async function deleteRunLifecycle(runId: string): Promise<void> {
  const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE run failed: ${res.status}`);
}
