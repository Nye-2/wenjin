"""Tests for email verification code generation rules."""

from src.services.email_service import EmailService


def test_generate_code_is_six_digit_numeric() -> None:
    service = EmailService()
    code = service._generate_code()

    assert len(code) == 6
    assert code.isdigit()
