import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";

export const SUPPORTED_BLOCK_ACTIONS = [
  "trigger_feature",
  "continue_thread",
  "open_feature",
  "rerun_from_artifact",
  "open_prism",
  "preview_prism_changes",
  "open_artifact",
  "rerun_feature",
  "resume_execution",
  "import_references",
] as const;

export type SupportedBlockAction = (typeof SUPPORTED_BLOCK_ACTIONS)[number];
type RouteSeedValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

const SUPPORTED_BLOCK_ACTION_SET = new Set<string>(SUPPORTED_BLOCK_ACTIONS);
const FEATURE_ROUTE_ACTIONS = new Set<SupportedBlockAction>([
  "trigger_feature",
  "open_feature",
  "rerun_from_artifact",
  "rerun_feature",
  "resume_execution",
  "import_references",
]);
const DEFAULT_ACTION_LABELS: Record<SupportedBlockAction, string> = {
  trigger_feature: "开始下一步",
  continue_thread: "继续在对话中处理",
  open_feature: "打开功能",
  rerun_from_artifact: "基于当前产物重跑",
  open_prism: "在 WenjinPrism 中继续编辑",
  preview_prism_changes: "预览待确认修改",
  open_artifact: "查看产物",
  rerun_feature: "重新运行",
  resume_execution: "继续执行",
  import_references: "导入参考资料",
};
const RESERVED_ROUTE_PARAM_KEYS = new Set([
  "action",
  "kind",
  "label",
  "url",
  "href",
  "feature_id",
  "project_id",
  "params",
  "skill_id",
  "item_id",
  "title",
  "name",
  "preview",
]);

export function isSupportedBlockAction(
  value: unknown,
): value is SupportedBlockAction {
  return typeof value === "string" && SUPPORTED_BLOCK_ACTION_SET.has(value);
}

export type ContinueThreadBlockAction = {
  action: "continue_thread";
  intent: string;
  source_block_kind: "question_card" | "result_card";
};

export function buildContinueThreadBlockAction(
  intent: string,
  sourceBlockKind: "question_card" | "result_card",
): ContinueThreadBlockAction {
  return {
    action: "continue_thread",
    intent,
    source_block_kind: sourceBlockKind,
  };
}

export interface ExecutionNextActionPresentation {
  action: SupportedBlockAction;
  href: string | null;
  label: string;
}

export function resolveExecutionNextActionPresentation(options: {
  actionRecord: Record<string, unknown>;
  workspaceId?: string | null;
  defaultFeatureId?: string | null;
  defaultExecutionId?: string | null;
  prismHref?: string | null;
}): ExecutionNextActionPresentation | null {
  const {
    actionRecord,
    workspaceId,
    defaultFeatureId,
    defaultExecutionId,
    prismHref,
  } = options;
  const actionName = readString(actionRecord.action) ?? readString(actionRecord.kind);
  if (!isSupportedBlockAction(actionName)) {
    return null;
  }

  const label = readString(actionRecord.label) ?? DEFAULT_ACTION_LABELS[actionName];
  const explicitHref = readString(actionRecord.url) ?? readString(actionRecord.href);

  if (actionName === "preview_prism_changes" || actionName === "open_prism") {
    return {
      action: actionName,
      href: buildWorkspacePrismHref(
        workspaceId ?? null,
        explicitHref ?? prismHref ?? null,
      ),
      label,
    };
  }

  if (explicitHref) {
    return { action: actionName, href: explicitHref, label };
  }

  if (actionName === "open_artifact") {
    return {
      action: actionName,
      href: buildWorkspaceRoomHref(workspaceId ?? null, actionRecord),
      label,
    };
  }

  if (!FEATURE_ROUTE_ACTIONS.has(actionName)) {
    return {
      action: actionName,
      href: null,
      label,
    };
  }

  const featureId = readString(actionRecord.feature_id) ?? defaultFeatureId ?? null;
  const routeParams = extractActionRouteParams(actionRecord);
  if (actionName === "resume_execution") {
    routeParams.entry = "resume";
    if (!routeParams.execution_id && defaultExecutionId) {
      routeParams.execution_id = defaultExecutionId;
    }
  }

  const href =
    workspaceId && featureId
      ? getWorkspaceFeatureRoute(workspaceId, featureId, routeParams)
      : null;

  return {
    action: actionName,
    href,
    label,
  };
}

function extractActionRouteParams(
  actionRecord: Record<string, unknown>,
): Record<string, RouteSeedValue> {
  const routeParams: Record<string, RouteSeedValue> = {};
  const nestedParams = readObject(actionRecord.params);
  if (nestedParams) {
    for (const [key, value] of Object.entries(nestedParams)) {
      const normalized = normalizeRouteSeedValue(value);
      if (normalized !== undefined) {
        routeParams[key] = normalized;
      }
    }
  }

  for (const [key, value] of Object.entries(actionRecord)) {
    if (RESERVED_ROUTE_PARAM_KEYS.has(key)) {
      continue;
    }
    const normalized = normalizeRouteSeedValue(value);
    if (normalized !== undefined) {
      routeParams[key] = normalized;
    }
  }

  const skillId = readString(actionRecord.skill_id);
  if (skillId && !routeParams.skill) {
    routeParams.skill = skillId;
  }

  return routeParams;
}

function normalizeRouteSeedValue(value: unknown): RouteSeedValue {
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    const normalized = value.filter(
      (item): item is string | number | boolean =>
        typeof item === "string" ||
        typeof item === "number" ||
        typeof item === "boolean",
    );
    return normalized.length > 0 ? normalized : undefined;
  }
  return undefined;
}

function buildWorkspaceRoomHref(
  workspaceId: string | null,
  actionRecord: Record<string, unknown>,
): string | null {
  if (!workspaceId) {
    return null;
  }

  const room = inferArtifactRoom(actionRecord);
  if (!room) {
    return null;
  }

  const query = new URLSearchParams();
  query.set("room", room);

  const artifactId = readString(actionRecord.artifact_id);
  if (artifactId) {
    query.set("artifact_id", artifactId);
  }

  const itemId = readString(actionRecord.item_id);
  if (itemId) {
    query.set("item_id", itemId);
  }

  const itemQuery =
    readString(actionRecord.title) ??
    readString(actionRecord.name) ??
    readString(actionRecord.preview);
  if (itemQuery) {
    query.set("query", itemQuery);
  }

  return `/workspaces/${workspaceId}?${query.toString()}`;
}

function buildWorkspacePrismHref(
  workspaceId: string | null,
  prismHref: string | null,
): string | null {
  if (workspaceId) {
    return `/workspaces/${workspaceId}/prism`;
  }
  return prismHref;
}

function inferArtifactRoom(
  actionRecord: Record<string, unknown>,
): "library" | "documents" | null {
  const explicitRoom = readString(actionRecord.room);
  if (explicitRoom === "library" || explicitRoom === "documents") {
    return explicitRoom;
  }

  const artifactKind =
    readString(actionRecord.artifact_kind) ??
    readString(actionRecord.output_kind) ??
    readString(actionRecord.artifact_type);

  if (artifactKind === "library_item" || artifactKind === "reference") {
    return "library";
  }
  if (artifactKind === "document" || artifactKind === "upload") {
    return "documents";
  }
  return null;
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}
