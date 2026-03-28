"""Parser for SKILL.md files."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def _coerce_text(value: object, default: str = "") -> str:
    """Normalize YAML scalar values to strings for ParsedSkill fields."""
    return value if isinstance(value, str) else default


def _coerce_string_list(value: object) -> list[str]:
    """Normalize YAML list values to a string-only list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass
class ParsedSkill:
    """Represents a parsed SKILL.md."""
    name: str = "unknown"
    description: str = ""
    license: str = "MIT"
    allowed_tools: list[str] = field(default_factory=list)
    prompt: str = ""
    source_path: str | None = None

    def get_subagent_calls(self) -> list[dict[str, str]]:
        """Extract subagent call patterns from the prompt.

        Returns:
            List of dicts with subagent_type and prompt
        """
        pattern = r'task\s*\(\s*subagent_type\s*=\s*["\']([^"\\\']+)["\']\s*,\s*prompt\s*=\s*["\']([^"\\\']+)["\']\s*\)'
        matches = re.findall(pattern, self.prompt)
        return [{"subagent_type": m[0], "prompt": m[1]} for m in matches]


class SkillParser:
    """Parser for SKILL.md files."""

    def parse(self, content: str) -> ParsedSkill:
        """Parse SKILL.md content.

        Args:
            content: The raw SKILL.md content

        Returns:
            ParsedSkill instance
        """
        skill = ParsedSkill()

        # Extract frontmatter
        frontmatter, prompt = self._extract_frontmatter(content)

        if frontmatter:
            skill.name = _coerce_text(frontmatter.get("name"), "unknown")
            skill.description = _coerce_text(frontmatter.get("description"))
            skill.license = _coerce_text(frontmatter.get("license"), "MIT")
            skill.allowed_tools = _coerce_string_list(frontmatter.get("allowed-tools"))

        skill.prompt = prompt
        return skill

    def parse_file(self, path: Path) -> ParsedSkill:
        """Parse a SKILL.md file.

        Args:
            path: Path to SKILL.md file

        Returns:
            ParsedSkill instance
        """
        content = path.read_text()
        skill = self.parse(content)
        skill.source_path = str(path)
        return skill

    def _extract_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Extract YAML frontmatter from content.

        Returns:
            Tuple of (frontmatter_dict, remaining_content)
        """
        if not content.startswith("---"):
            return {}, content

        # Find the closing ---
        end_match = re.search(r'\n---\s*\n', content[3:])
        if not end_match:
            return {}, content

        frontmatter_str = content[3:end_match.start() + 3]
        remaining = content[end_match.end() + 3:]

        try:
            loaded = yaml.safe_load(frontmatter_str)
            frontmatter = (
                {str(key): value for key, value in loaded.items()}
                if isinstance(loaded, dict)
                else {}
            )
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, remaining
