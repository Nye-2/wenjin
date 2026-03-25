import type { Artifact, Workspace } from "@/stores/workspace";
import {
  findArtifactById,
  findLatestArtifact,
  getArtifactContentRecord,
  readNamedSections,
  readString,
} from "@/lib/artifact-utils";

const FEATURE_SOURCE_TYPES: Record<string, string[]> = {
  literature_management: [
    "deep_research_report",
    "literature_inventory",
    "literature_review",
    "literature_search_results",
  ],
  paper_analysis: ["paper_analysis"],
  writing: [
    "framework_outline",
    "paper_analysis",
    "literature_review",
    "paper_draft",
  ],
  literature_review: [
    "literature_search_results",
    "paper_analysis",
    "framework_outline",
    "paper_draft",
  ],
  framework_outline: [
    "literature_review",
    "paper_analysis",
    "paper_draft",
    "literature_search_results",
  ],
  peer_review: [
    "paper_draft",
    "framework_outline",
    "paper_analysis",
    "thesis_chapter",
  ],
  journal_recommend: [
    "framework_outline",
    "paper_draft",
    "paper_analysis",
    "literature_review",
  ],
  experiment_design: [
    "proposal",
    "background_research",
    "methodology",
  ],
  copyright_materials: ["copyright_materials"],
  technical_description: [
    "technical_description",
    "copyright_materials",
  ],
  patent_outline: ["patent_outline"],
  prior_art_search: ["prior_art_report", "patent_outline"],
};

function artifactContent(artifact: Artifact | null | undefined): Record<string, unknown> {
  return getArtifactContentRecord(artifact) ?? {};
}

function readRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function formatSectionsForPrompt(value: unknown, maxItems: number = 4): string | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const parts = value
    .slice(0, maxItems)
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const record = item as Record<string, unknown>;
      const title =
        readString(record.title) ?? readString(record.name) ?? readString(record.id);
      const content = readString(record.content) ?? readString(record.focus);
      if (!title && !content) {
        return null;
      }
      return [title, content].filter(Boolean).join(": ");
    })
    .filter((item): item is string => Boolean(item));

  return parts.length > 0 ? parts.join("\n") : null;
}

export function resolveFeatureSourceArtifact(
  featureId: string,
  artifacts: Artifact[],
  explicitArtifactId?: string | null
): Artifact | null {
  const explicitArtifact = findArtifactById(artifacts, explicitArtifactId);
  if (explicitArtifact) {
    return explicitArtifact;
  }
  const acceptedTypes = FEATURE_SOURCE_TYPES[featureId];
  if (!acceptedTypes) {
    return null;
  }
  return findLatestArtifact(artifacts, acceptedTypes);
}

export function getArtifactPaperTitle(
  artifact: Artifact | null | undefined
): string | null {
  const content = artifactContent(artifact);
  return (
    readString(content.paper_title) ??
    readString(content.title) ??
    readString(artifact?.title)
  );
}

export function getArtifactTopic(
  artifact: Artifact | null | undefined
): string | null {
  const content = artifactContent(artifact);
  return (
    readString(content.topic) ??
    readString(content.keywords) ??
    readString(content.query) ??
    getArtifactPaperTitle(artifact) ??
    readString(artifact?.title)
  );
}

export function getArtifactDiscipline(
  artifact: Artifact | null | undefined,
  workspace: Workspace | null | undefined
): string | null {
  const content = artifactContent(artifact);
  return readString(content.discipline) ?? readString(workspace?.discipline);
}

export function getArtifactSoftwareProfile(
  artifact: Artifact | null | undefined
): Record<string, unknown> | null {
  const content = artifactContent(artifact);
  return readRecord(content.software_profile);
}

export function getArtifactAbstract(
  artifact: Artifact | null | undefined
): string | null {
  const content = artifactContent(artifact);
  if (!artifact) {
    return null;
  }

  if (artifact.type === "framework_outline") {
    return readString(content.abstract);
  }
  if (artifact.type === "paper_analysis") {
    return readString(content.summary);
  }
  if (artifact.type === "literature_review") {
    return readString(content.summary);
  }
  if (artifact.type === "deep_research_report") {
    const discovery = readRecord(content.discovery);
    return readString(discovery?.summary) ?? readString(content.topic);
  }
  if (artifact.type === "paper_draft") {
    return readString(content.content);
  }

  return readString(content.abstract) ?? readString(content.summary);
}

export function getArtifactExcerpt(
  artifact: Artifact | null | undefined
): string | null {
  const content = artifactContent(artifact);
  if (!artifact) {
    return null;
  }

  if (artifact.type === "paper_draft") {
    return readString(content.content);
  }
  if (artifact.type === "thesis_chapter") {
    return readString(content.markdown) ?? readString(content.content);
  }
  if (artifact.type === "framework_outline") {
    const abstract = readString(content.abstract);
    const sections = formatSectionsForPrompt(content.sections);
    const contributions = Array.isArray(content.contributions)
      ? (content.contributions as unknown[])
          .map((item) => readString(item))
          .filter((item): item is string => Boolean(item))
          .slice(0, 4)
          .join("\n")
      : null;
    return [abstract, sections, contributions].filter(Boolean).join("\n\n") || null;
  }
  if (artifact.type === "paper_analysis") {
    const summary = readString(content.summary);
    const sections = content.sections;
    if (sections && typeof sections === "object" && !Array.isArray(sections)) {
      const normalized = Object.values(sections as Record<string, unknown>)
        .slice(0, 4)
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }
          const record = item as Record<string, unknown>;
          const title = readString(record.title);
          const body = readString(record.content);
          if (!title && !body) {
            return null;
          }
          return [title, body].filter(Boolean).join(": ");
        })
        .filter((item): item is string => Boolean(item))
        .join("\n");
      return [summary, normalized].filter(Boolean).join("\n\n") || null;
    }
    return summary;
  }
  if (artifact.type === "deep_research_report") {
    const discovery = readRecord(content.discovery);
    const summary = readString(discovery?.summary);
    const ideas = Array.isArray(content.ideas)
      ? (content.ideas as unknown[])
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null;
            }
            const record = item as Record<string, unknown>;
            return readString(record.title) ?? readString(record.description);
          })
          .filter((item): item is string => Boolean(item))
          .slice(0, 4)
          .join("\n")
      : null;
    const gaps = Array.isArray(content.gaps)
      ? (content.gaps as unknown[])
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null;
            }
            return readString((item as Record<string, unknown>).description);
          })
          .filter((item): item is string => Boolean(item))
          .slice(0, 3)
          .join("\n")
      : null;
    return [
      readString(content.topic),
      summary,
      ideas ? `研究创意\n${ideas}` : null,
      gaps ? `研究空白\n${gaps}` : null,
    ]
      .filter(Boolean)
      .join("\n\n") || null;
  }

  return (
    readString(content.content) ??
    readString(content.summary) ??
    readString(content.abstract)
  );
}

export function getArtifactObjective(
  artifact: Artifact | null | undefined
): string | null {
  const content = artifactContent(artifact);
  if (!artifact) {
    return null;
  }

  if (artifact.type === "proposal") {
    const sections = Array.isArray(content.sections) ? content.sections : [];
    const objectiveSection = sections.find((item) => {
      if (!item || typeof item !== "object") {
        return false;
      }
      const record = item as Record<string, unknown>;
      const sectionId = readString(record.id) ?? "";
      const title = readString(record.title) ?? "";
      return sectionId === "objectives" || title.includes("目标");
    });
    if (objectiveSection && typeof objectiveSection === "object") {
      return readString((objectiveSection as Record<string, unknown>).content);
    }
  }

  if (artifact.type === "background_research") {
    return readString(content.keywords) ?? readString(content.summary);
  }

  if (artifact.type === "methodology") {
    return readString(content.objective) ?? readString(content.topic);
  }

  return readString(content.objective);
}

export function summarizeArtifactContext(
  artifact: Artifact | null | undefined
): string | null {
  if (!artifact) {
    return null;
  }
  const content = artifactContent(artifact);
  return (
    readString(content.summary) ??
    readString(content.abstract) ??
    readString(content.objective) ??
    readString(content.topic) ??
    (Array.isArray(content.sections)
      ? readNamedSections(content.sections, 3).join("、")
      : null) ??
    readString(artifact.title)
  );
}
