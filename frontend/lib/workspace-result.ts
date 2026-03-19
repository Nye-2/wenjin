import type { WorkspaceResultViewModel } from "@/components/workspace/WorkspaceResultPanel";

type ResultValue = string | number | null | undefined;

export function describeFields(
  fields: Array<[label: string, value: ResultValue]>,
  fallback: string = "未填写"
): string {
  return fields
    .map(([label, value]) => `${label}：${value === null || value === undefined || value === "" ? fallback : value}`)
    .join("；");
}

export function describeTaskStatus(options: {
  error: string | null;
  status: string | null;
  idleMessage: string;
  loadingMessage?: string;
  isLoading?: boolean;
}): string {
  if (options.isLoading && options.loadingMessage) {
    return options.loadingMessage;
  }
  if (options.error) {
    return `执行失败：${options.error}`;
  }
  if (options.status) {
    return `执行反馈：${options.status}`;
  }
  return options.idleMessage;
}

export function createWorkspaceResultViewModel(
  viewModel: WorkspaceResultViewModel
): WorkspaceResultViewModel {
  return viewModel;
}
