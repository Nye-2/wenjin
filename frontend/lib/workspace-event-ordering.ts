import type { ThreadSummary, WorkspaceActivityItem } from './api';

function parseTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareTimestamps(
  incoming: string | null | undefined,
  existing: string | null | undefined
): number {
  const incomingTs = parseTimestamp(incoming);
  const existingTs = parseTimestamp(existing);

  if (incomingTs === null && existingTs === null) {
    return 0;
  }
  if (incomingTs === null) {
    return -1;
  }
  if (existingTs === null) {
    return 1;
  }
  return incomingTs - existingTs;
}

function activityStatusRank(status: string | null | undefined): number {
  switch (status) {
    case 'pending':
      return 1;
    case 'running':
    case 'awaiting_user_input':
      return 2;
    case 'success':
    case 'completed':
    case 'failed':
    case 'cancelled':
    case 'timed_out':
      return 3;
    default:
      return 0;
  }
}

function activityProgressValue(item: WorkspaceActivityItem): number {
  const progress = item.metadata?.progress;
  return typeof progress === 'number' ? progress : -1;
}

export function shouldReplaceWorkspaceActivity(
  existing: WorkspaceActivityItem | undefined,
  incoming: WorkspaceActivityItem
): boolean {
  if (!existing) {
    return true;
  }

  const timestampDelta = compareTimestamps(incoming.occurred_at, existing.occurred_at);
  if (timestampDelta < 0) {
    return false;
  }
  if (timestampDelta > 0) {
    return true;
  }

  const statusDelta =
    activityStatusRank(incoming.status) - activityStatusRank(existing.status);
  if (statusDelta !== 0) {
    return statusDelta > 0;
  }

  return activityProgressValue(incoming) >= activityProgressValue(existing);
}

function sortActivitiesDesc(
  left: WorkspaceActivityItem,
  right: WorkspaceActivityItem
): number {
  const leftTime = parseTimestamp(left.occurred_at);
  const rightTime = parseTimestamp(right.occurred_at);
  if (leftTime === null || rightTime === null) {
    return (right.occurred_at || '').localeCompare(left.occurred_at || '');
  }
  return rightTime - leftTime;
}

export function upsertWorkspaceActivityList(
  items: WorkspaceActivityItem[],
  incoming: WorkspaceActivityItem,
  limit: number
): WorkspaceActivityItem[] {
  const existing = items.find((item) => item.id === incoming.id);
  if (!shouldReplaceWorkspaceActivity(existing, incoming)) {
    return items;
  }

  return [incoming, ...items.filter((item) => item.id !== incoming.id)]
    .sort(sortActivitiesDesc)
    .slice(0, limit);
}

export function shouldReplaceThreadSummary(
  existing: ThreadSummary | undefined,
  incoming: ThreadSummary
): boolean {
  if (!existing) {
    return true;
  }

  const timestampDelta = compareTimestamps(incoming.updated_at, existing.updated_at);
  if (timestampDelta < 0) {
    return false;
  }
  if (timestampDelta > 0) {
    return true;
  }

  const incomingCount = incoming.message_count ?? 0;
  const existingCount = existing.message_count ?? 0;
  if (incomingCount !== existingCount) {
    return incomingCount >= existingCount;
  }

  return true;
}

function sortThreadsDesc(left: ThreadSummary, right: ThreadSummary): number {
  const leftTime = parseTimestamp(left.updated_at);
  const rightTime = parseTimestamp(right.updated_at);
  if (leftTime === null || rightTime === null) {
    return (right.updated_at || '').localeCompare(left.updated_at || '');
  }
  return rightTime - leftTime;
}

export function upsertThreadSummaryList(
  threads: ThreadSummary[],
  incoming: ThreadSummary
): ThreadSummary[] {
  const existing = threads.find((thread) => thread.id === incoming.id);
  if (!shouldReplaceThreadSummary(existing, incoming)) {
    return threads;
  }

  return [incoming, ...threads.filter((thread) => thread.id !== incoming.id)].sort(
    sortThreadsDesc
  );
}
