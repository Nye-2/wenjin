"""Tests for deployment bootstrap catalog seeding behavior."""

from pathlib import Path


def test_bootstrap_admin_syncs_capability_seed_updates_incrementally() -> None:
    source = Path("src/database/bootstrap_admin.py").read_text(encoding="utf-8")

    capability_section = source.split("from src.services.capability_loader import CapabilityLoader", maxsplit=1)[1]
    capability_section = capability_section.split("except Exception as cap_exc", maxsplit=1)[0]
    assert "loader.sync_seed_updates()" in capability_section
    assert "loader.load_seeds_if_empty()" not in capability_section
