"""Tests for deployment bootstrap catalog seeding behavior."""

from pathlib import Path


def test_bootstrap_admin_syncs_capability_seed_updates_incrementally() -> None:
    source = Path("src/database/bootstrap_admin.py").read_text(encoding="utf-8")

    capability_section = source.split("from src.services.capability_loader import CapabilityLoader", maxsplit=1)[1]
    capability_section = capability_section.split("except Exception as cap_exc", maxsplit=1)[0]
    assert "loader.sync_seed_updates()" in capability_section
    assert "loader.load_seeds_if_empty()" not in capability_section


def test_bootstrap_admin_syncs_agent_template_seed_updates_incrementally() -> None:
    source = Path("src/database/bootstrap_admin.py").read_text(encoding="utf-8")

    template_section = source.split("from src.services.agent_template_loader import AgentTemplateLoader", maxsplit=1)[1]
    template_section = template_section.split("except Exception as template_exc", maxsplit=1)[0]
    assert "template_loader.sync_seed_updates()" in template_section
    assert "template_loader.load_seeds_if_empty()" not in template_section
