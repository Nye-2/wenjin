"""Tests for SKILL.md parsing."""

import tempfile
from pathlib import Path

from src.skills.parser import SkillParser, ParsedSkill


class TestSkillParser:
    def test_parse_skill_frontmatter(self):
        """Should parse YAML frontmatter from SKILL.md."""
        content = """---
name: test-skill
description: A test skill
allowed-tools:
  - read_file
  - semantic_scholar_search
---

# Test Skill

This is a test skill.
"""
        parser = SkillParser()
        skill = parser.parse(content)
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert "read_file" in skill.allowed_tools

    def test_parse_skill_without_frontmatter(self):
        """Should handle SKILL.md without frontmatter."""
        content = """# Test Skill

Just a simple skill.
"""
        parser = SkillParser()
        skill = parser.parse(content)
        assert skill.name == "unknown"
        assert skill.prompt == content

    def test_extract_subagent_calls(self):
        """Should extract subagent call patterns from skill prompt."""
        content = """---
name: research
---

# Research Skill

1. Call scout: task(subagent_type="scout", prompt="Search for papers")
2. Then analyze: task(subagent_type="analyst", prompt="Analyze results")
"""
        parser = SkillParser()
        skill = parser.parse(content)
        calls = skill.get_subagent_calls()
        assert len(calls) == 2
        assert calls[0]["subagent_type"] == "scout"
        assert calls[1]["subagent_type"] == "analyst"

    def test_parse_file(self, tmp_path):
        """Should parse a SKILL.md file."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: file-skill
description: From file
---
# Content
""")
        parser = SkillParser()
        skill = parser.parse_file(skill_file)
        assert skill.name == "file-skill"
