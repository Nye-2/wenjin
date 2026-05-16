"""Tests for redeem code generator."""

import re

from src.services.redeem_code_generator import generate_code, ALPHABET


def test_format_is_four_groups_of_four():
    code = generate_code()
    assert re.match(r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$", code), code


def test_uses_only_safe_alphabet():
    for _ in range(50):
        code = generate_code()
        for ch in code.replace("-", ""):
            assert ch in ALPHABET, f"forbidden char {ch} in {code}"


def test_high_entropy():
    """No two codes from 1000 generations should collide (probabilistic, but virtually certain)."""
    codes = {generate_code() for _ in range(1000)}
    assert len(codes) == 1000
