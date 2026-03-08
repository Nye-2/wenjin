"""Skill loader for discovering and loading academic skills."""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


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


def load_skills(
    skills_path: str = "./skills/public",
    config_path: str = "./extensions_config.json",
) -> list[Skill]:
    """Load all skills from the skills directory.

    Args:
        skills_path: Path to skills directory
        config_path: Path to extensions config for enabled state

    Returns:
        List of loaded Skill objects
    """
    skills_dir = Path(skills_path)
    if not skills_dir.exists():
        return []

    # Load enabled state from config
    enabled_skills = _load_enabled_skills(config_path)

    skills = []
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skill = _parse_skill(skill_file, enabled_skills)
                if skill:
                    skills.append(skill)

    return skills


def _load_enabled_skills(config_path: str) -> dict[str, bool]:
    """Load skill enabled states from config file.

    Args:
        config_path: Path to extensions_config.json

    Returns:
        Dict of skill_name -> enabled
    """
    config_file = Path(config_path)
    if not config_file.exists():
        return {}

    try:
        with open(config_file) as f:
            config = json.load(f)
        return config.get("skills", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_skill(skill_file: Path, enabled_skills: dict[str, bool]) -> Skill | None:
    """Parse a SKILL.md file into a Skill object.

    Args:
        skill_file: Path to SKILL.md
        enabled_skills: Dict of enabled states

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
        skill_key = name.lower().replace("-", "_").replace(" ", "_")
        enabled = enabled_skills.get(name, enabled_skills.get(skill_key, True))

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
