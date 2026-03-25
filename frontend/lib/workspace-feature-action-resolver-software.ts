import { readString, readStringArrayLike } from "@/lib/artifact-utils";
import { getArtifactSoftwareProfile } from "@/lib/workspace-feature-action-artifacts";
import {
  buildFeatureActionState,
  withSourceArtifact,
} from "@/lib/workspace-feature-action-state-support";
import type { FeatureActionResolver } from "@/lib/workspace-feature-action-types";

export const softwareFeatureActionResolvers: Record<string, FeatureActionResolver> = {
  copyright_materials: (context) => {
    const softwareProfile = getArtifactSoftwareProfile(context.sourceArtifact);
    const softwareName =
      readString(context.orchestrationParams?.software_name) ??
      readString(softwareProfile?.software_name) ??
      readString(context.workspace?.name) ??
      "待确认软件";
    const version =
      readString(context.orchestrationParams?.version) ??
      readString(softwareProfile?.version) ??
      "V1.0";
    const applicantName =
      readString(context.orchestrationParams?.applicant_name) ??
      readString(softwareProfile?.applicant_name);
    const completionDate =
      readString(context.orchestrationParams?.completion_date) ??
      readString(softwareProfile?.completion_date);
    const highlights =
      readStringArrayLike(context.orchestrationParams?.highlights).length > 0
        ? readStringArrayLike(context.orchestrationParams?.highlights)
        : readStringArrayLike(softwareProfile?.highlights);
    const targetPlatforms =
      readStringArrayLike(context.orchestrationParams?.target_platforms).length > 0
        ? readStringArrayLike(context.orchestrationParams?.target_platforms)
        : readStringArrayLike(softwareProfile?.target_platforms);
    const sourceModules =
      readStringArrayLike(context.orchestrationParams?.source_modules).length > 0
        ? readStringArrayLike(context.orchestrationParams?.source_modules)
        : readStringArrayLike(softwareProfile?.source_modules);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        software_name: softwareName,
        version,
        applicant_name: applicantName,
        completion_date: completionDate,
        highlights: highlights.length > 0 ? highlights : undefined,
        target_platforms: targetPlatforms.length > 0 ? targetPlatforms : undefined,
        source_modules: sourceModules.length > 0 ? sourceModules : undefined,
      }),
      rerunParams: softwareName
        ? {
            software_name: softwareName,
            version,
            applicant_name: applicantName ?? undefined,
            completion_date: completionDate ?? undefined,
            highlights: highlights.length > 0 ? highlights : undefined,
            target_platforms: targetPlatforms.length > 0 ? targetPlatforms : undefined,
            source_modules: sourceModules.length > 0 ? sourceModules : undefined,
          }
        : null,
      rerunUnavailableReason: softwareName
        ? null
        : "缺少可复用的软件基础信息。",
    });
  },
  technical_description: (context) => {
    const softwareProfile = getArtifactSoftwareProfile(context.sourceArtifact);
    const softwareName =
      readString(context.orchestrationParams?.software_name) ??
      readString(softwareProfile?.software_name) ??
      readString(context.workspace?.name) ??
      "待确认软件";
    const version =
      readString(context.orchestrationParams?.version) ??
      readString(softwareProfile?.version) ??
      "V1.0";
    const coreModules =
      readStringArrayLike(context.orchestrationParams?.core_modules).length > 0
        ? readStringArrayLike(context.orchestrationParams?.core_modules)
        : readStringArrayLike(softwareProfile?.core_modules);
    const deploymentArchitecture =
      readString(context.orchestrationParams?.deployment_architecture) ??
      readString(softwareProfile?.deployment_architecture) ??
      "B/S架构";
    const databaseMiddleware =
      readStringArrayLike(context.orchestrationParams?.database_middleware).length > 0
        ? readStringArrayLike(context.orchestrationParams?.database_middleware)
        : readStringArrayLike(softwareProfile?.database_middleware);
    const interfaceProtocols =
      readStringArrayLike(context.orchestrationParams?.interface_protocols).length > 0
        ? readStringArrayLike(context.orchestrationParams?.interface_protocols)
        : readStringArrayLike(softwareProfile?.interface_protocols);
    const highlights =
      readStringArrayLike(context.orchestrationParams?.highlights).length > 0
        ? readStringArrayLike(context.orchestrationParams?.highlights)
        : readStringArrayLike(softwareProfile?.highlights);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        software_name: softwareName,
        version,
        core_modules: coreModules.length > 0 ? coreModules : undefined,
        deployment_architecture: deploymentArchitecture,
        database_middleware:
          databaseMiddleware.length > 0 ? databaseMiddleware : undefined,
        interface_protocols:
          interfaceProtocols.length > 0 ? interfaceProtocols : undefined,
        highlights: highlights.length > 0 ? highlights : undefined,
      }),
      rerunParams: softwareName
        ? {
            software_name: softwareName,
            version,
            core_modules: coreModules.length > 0 ? coreModules : undefined,
            deployment_architecture: deploymentArchitecture,
            database_middleware:
              databaseMiddleware.length > 0 ? databaseMiddleware : undefined,
            interface_protocols:
              interfaceProtocols.length > 0 ? interfaceProtocols : undefined,
            highlights: highlights.length > 0 ? highlights : undefined,
          }
        : null,
      rerunUnavailableReason: softwareName
        ? null
        : "缺少可复用的软件技术信息。",
    });
  },
};
