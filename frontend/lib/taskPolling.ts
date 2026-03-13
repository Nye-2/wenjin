import { getTaskStatus, type TaskStatus } from "@/lib/api";

export interface PollTaskOptions {
  maxAttempts?: number;
  intervalMs?: number;
  onProgress?: (task: TaskStatus) => void;
}

const wait = (ms: number) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });

const isTerminalStatus = (status: string) =>
  status === "success" || status === "failed" || status === "cancelled";

export async function pollTaskUntilTerminal(
  taskId: string,
  options: PollTaskOptions = {}
): Promise<TaskStatus | null> {
  const { maxAttempts = 120, intervalMs = 2000, onProgress } = options;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const task = await getTaskStatus(taskId);
    if (isTerminalStatus(task.status)) {
      return task;
    }

    onProgress?.(task);
    await wait(intervalMs);
  }

  return null;
}
