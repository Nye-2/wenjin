export function languageForPath(path: string | null): string {
  const lower = (path || "").toLowerCase();
  if (lower.endsWith(".bib")) return "bibtex";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".md")) return "markdown";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".tex") || lower.endsWith(".sty") || lower.endsWith(".cls")) {
    return "latex";
  }
  return "plaintext";
}

export function isTextFile(path: string): boolean {
  const lower = path.toLowerCase();
  return [
    ".tex",
    ".bib",
    ".cls",
    ".sty",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
  ].some((suffix) => lower.endsWith(suffix));
}

export function isImageFile(path: string): boolean {
  return [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"].some((suffix) =>
    path.toLowerCase().endsWith(suffix),
  );
}
