"""Tests for skill loader extensions-config integration."""

from __future__ import annotations

import json

from src.config.extensions_config import ExtensionsConfig, reset_extensions_config, set_extensions_config
from src.skills.loader import load_skills


def test_load_skills_respects_extensions_skill_enabled_state(tmp_path):
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "deep-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: deep-research\n"
        "description: Deep research workflow\n"
        "license: MIT\n"
        "allowed-tools: [read_file]\n"
        "---\n"
        "Skill body\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {},
                "skills": {
                    "deep-research": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )

    skills = load_skills(str(skills_dir), str(config_path))

    assert len(skills) == 1
    assert skills[0].name == "deep-research"
    assert skills[0].enabled is False


def test_load_skills_defaults_public_skills_to_enabled(tmp_path):
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "framework-designer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: framework-designer\n"
        "description: Framework designer workflow\n"
        "license: MIT\n"
        "allowed-tools: [read_file]\n"
        "---\n"
        "Skill body\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {}, "skills": {}}),
        encoding="utf-8",
    )

    skills = load_skills(str(skills_dir), str(config_path))

    assert len(skills) == 1
    assert skills[0].enabled is True


def test_load_skills_uses_cached_extensions_config_when_path_omitted(tmp_path):
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "peer-reviewer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: peer-reviewer\n"
        "description: Peer reviewer workflow\n"
        "license: MIT\n"
        "allowed-tools: [read_file]\n"
        "---\n"
        "Skill body\n",
        encoding="utf-8",
    )

    set_extensions_config(
        ExtensionsConfig.model_validate(
            {"mcpServers": {}, "skills": {"peer-reviewer": {"enabled": False}}}
        )
    )
    try:
        skills = load_skills(str(skills_dir))
    finally:
        reset_extensions_config()

    assert len(skills) == 1
    assert skills[0].enabled is False
