"""Skill loader for discovering and loading academic skills."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.config.extensions_config import ExtensionsConfig, get_extensions_config


@dataclass
class Skill:
    """Represents a loaded skill."""
    name: str
    description: str
    license: str
    allowed_tools: tuple
    content: str
    path: Path
    enabled: bool = True


def _default_skills_path() -> Path:
    """Return the stable public skills directory path."""
    return Path(__file__).resolve().parents[2] / "skills" / "public"


def load_skills(
    skills_path: str | Path | None = None,
    config_path: str | None = None,
) -> list[Skill]:
    """Load all skills from the skills directory.

    Args:
        skills_path: Path to skills directory
        config_path: Optional explicit extensions config for enabled state

    Returns:
        List of loaded Skill objects
    """
    skills_dir = Path(skills_path) if skills_path is not None else _default_skills_path()
    if not skills_dir.exists():
        return []

    extensions_config = (
        ExtensionsConfig.from_file(config_path)
        if config_path is not None
        else get_extensions_config()
    )

    skills = []
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skill = _parse_skill(skill_file, extensions_config)
                if skill:
                    skills.append(skill)

    return skills


def _parse_skill(skill_file: Path, extensions_config: ExtensionsConfig) -> Skill | None:
    """Parse a SKILL.md file into a Skill object.

    Args:
        skill_file: Path to SKILL.md
        extensions_config: Unified extensions config

    Returns:
        Skill object or None if parsing fails
    """
    try:
        content = skill_file.read_text()

        # Parse YAML frontmatter
        if not content.startswith("---"):
            return None

        # Find the end of frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter = yaml.safe_load(parts[1])
        skill_content = parts[2].strip()

        # Extract fields
        name = frontmatter.get("name", skill_file.parent.name)
        description = frontmatter.get("description", "")
        license_str = frontmatter.get("license", "MIT")
        allowed_tools = tuple(frontmatter.get("allowed-tools", []))

        # Get enabled state
        enabled = extensions_config.is_skill_enabled(name, "public")

        return Skill(
            name=name,
            description=description,
            license=license_str,
            allowed_tools=allowed_tools,
            content=skill_content,
            path=skill_file,
            enabled=enabled,
        )

    except Exception as e:
        print(f"Error parsing skill {skill_file}: {e}")
        return None
