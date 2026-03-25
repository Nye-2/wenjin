import { readString, readStringArrayLike } from "@/lib/artifact-utils";
import {
  buildFeatureActionState,
  withSourceArtifact,
} from "@/lib/workspace-feature-action-state-support";
import type { FeatureActionResolver } from "@/lib/workspace-feature-action-types";

export const patentFeatureActionResolvers: Record<string, FeatureActionResolver> = {
  patent_outline: (context) => {
    const content = context.sourceArtifact?.content ?? {};
    const innovationDescription =
      readString(context.orchestrationParams?.innovation_description) ??
      readString(content.innovation_description) ??
      readString(context.workspace?.description) ??
      readString(context.workspace?.name) ??
      context.fallbackTaskName;
    const technicalField =
      readString(context.orchestrationParams?.technical_field) ??
      readString(content.technical_field) ??
      readString(context.workspace?.discipline);
    const applicationScenario =
      readString(context.orchestrationParams?.application_scenario) ??
      readString(content.application_scenario);
    const implementationMethod =
      readString(context.orchestrationParams?.implementation_method) ??
      readString(content.implementation_method);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        innovation_description: innovationDescription,
        technical_field: technicalField,
        application_scenario: applicationScenario,
        implementation_method: implementationMethod,
      }),
      rerunParams: innovationDescription
        ? {
            innovation_description: innovationDescription,
            technical_field: technicalField ?? undefined,
            application_scenario: applicationScenario ?? undefined,
            implementation_method: implementationMethod ?? undefined,
          }
        : null,
      rerunUnavailableReason: innovationDescription
        ? null
        : "缺少可复用的创新点描述。",
    });
  },
  prior_art_search: (context) => {
    const content = context.sourceArtifact?.content ?? {};
    const keywords =
      readStringArrayLike(context.orchestrationParams?.keywords).length > 0
        ? readStringArrayLike(context.orchestrationParams?.keywords)
        : readStringArrayLike(content.keywords).length > 0
          ? readStringArrayLike(content.keywords)
          : [
              readString(content.innovation_description) ??
                readString(context.workspace?.name) ??
                context.fallbackTaskName,
              readString(content.technical_field),
              readString(content.application_scenario),
            ].filter((item): item is string => Boolean(item));
    const ipcCodes =
      readStringArrayLike(context.orchestrationParams?.ipc_codes).length > 0
        ? readStringArrayLike(context.orchestrationParams?.ipc_codes)
        : readStringArrayLike(content.ipc_codes);
    const timeRange =
      readString(context.orchestrationParams?.time_range) ??
      readString(content.time_range) ??
      "近5年";
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        keywords: keywords.length > 0 ? keywords : undefined,
        ipc_codes: ipcCodes.length > 0 ? ipcCodes : undefined,
        time_range: timeRange,
      }),
      rerunParams: keywords.length > 0
        ? {
            keywords,
            ipc_codes: ipcCodes.length > 0 ? ipcCodes : undefined,
            time_range: timeRange,
          }
        : null,
      rerunUnavailableReason: keywords.length > 0
        ? null
        : "缺少可复用的检索关键词。",
    });
  },
};
