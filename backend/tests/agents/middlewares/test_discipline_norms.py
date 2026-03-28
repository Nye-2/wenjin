"""Tests for externalized discipline norms."""

from pathlib import Path

import yaml

from src.agents.middlewares.discipline_context import (
    DisciplineRegistry,
    DISCIPLINE_NORMS_PATH,
)


def test_discipline_norms_yaml_exists():
    assert DISCIPLINE_NORMS_PATH.exists()


def test_discipline_norms_yaml_is_valid():
    data = yaml.safe_load(DISCIPLINE_NORMS_PATH.read_text(encoding="utf-8"))
    assert "disciplines" in data
    assert "workspace_types" in data
    assert len(data["disciplines"]) >= 4


def test_registry_loads_from_yaml():
    registry = DisciplineRegistry()
    norms = registry.get_norms("computer_science")
    assert norms["citation_style"] == "IEEE"
    assert "structure" in norms


def test_registry_falls_back_on_unknown_discipline():
    registry = DisciplineRegistry()
    norms = registry.get_norms("unknown_field")
    assert norms["citation_style"] == "IEEE"


def test_registry_merges_workspace_type():
    registry = DisciplineRegistry()
    norms = registry.get_norms("biology", workspace_type="thesis")
    assert "paper_length" in norms
    assert norms["citation_style"] == "APA"
