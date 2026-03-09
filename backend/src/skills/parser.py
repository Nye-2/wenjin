"""Parser for SKILL.md files."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ParsedSkill:
    """Represents a parsed SKILL.md."""
    name: str = "unknown"
    description: str = ""
    license: str = "MIT"
    allowed_tools: list[str] = field(default_factory=list)
    prompt: str = ""
    source_path: str | None = None

    def get_subagent_calls(self) -> list[dict]:
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
            skill.name = frontmatter.get("name", "unknown")
            skill.description = frontmatter.get("description", "")
            skill.license = frontmatter.get("license", "MIT")
            skill.allowed_tools = frontmatter.get("allowed-tools", [])

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

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
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
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, remaining
