"""Unit tests for ``EmailSender`` protocol + ``SmtpEmailSender`` / ``FakeEmailSender``.

Strict-TDD coverage for:
- FakeEmailSender records / retrieves sent tuples
- SmtpEmailSender builds correct EmailMessage and controls starttls/login
- Security regression: code and raw email must NEVER appear in logs
- Protocol conformance: both impls accepted where EmailSender is expected
"""

from __future__ import annotations

import hashlib
import logging
import smtplib
from email.message import EmailMessage
from typing import get_type_hints
from unittest.mock import MagicMock, call, patch

import pytest

from openwellness_api.auth.email_sender import (
    EmailSender,
    FakeEmailSender,
    SmtpEmailSender,
)
from openwellness_api.config import SmtpSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _smtp_settings(**overrides: object) -> SmtpSettings:
    base: dict[str, object] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "sender@example.com",
        "password": "secret",
        "use_tls": True,
        "from_address": "noreply@example.com",
    }
    base.update(overrides)
    return SmtpSettings(**base)  # type: ignore[arg-type]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ===========================================================================
# FakeEmailSender
# ===========================================================================

class TestFakeEmailSender:
    """``FakeEmailSender`` records sends and exposes a helper lookup."""

    def test_records_single_send(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="123456", purpose="login")
        assert fake.sent == [("a@b.com", "123456", "login")]

    def test_last_code_returns_most_recent_for_email(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="123456", purpose="login")
        assert fake.last_code("a@b.com") == "123456"

    def test_last_code_filters_by_purpose(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="123456", purpose="login")
        assert fake.last_code("a@b.com", "registration") is None

    def test_last_code_unknown_email_returns_none(self) -> None:
        fake = FakeEmailSender()
        assert fake.last_code("unknown@example.com") is None

    def test_last_code_returns_latest_when_multiple_sends(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="111111", purpose="login")
        fake.send_otp(email="a@b.com", code="222222", purpose="login")
        assert fake.last_code("a@b.com") == "222222"

    def test_records_multiple_sends(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="111111", purpose="login")
        fake.send_otp(email="x@y.com", code="999999", purpose="registration")
        assert len(fake.sent) == 2
        assert fake.sent[0] == ("a@b.com", "111111", "login")
        assert fake.sent[1] == ("x@y.com", "999999", "registration")

    def test_ttl_seconds_accepted_without_error(self) -> None:
        fake = FakeEmailSender()
        # Should not raise; ttl_seconds is accepted but irrelevant to Fake
        fake.send_otp(email="a@b.com", code="123456", purpose="login", ttl_seconds=600)
        assert fake.sent == [("a@b.com", "123456", "login")]

    def test_last_code_filters_by_purpose_matches(self) -> None:
        fake = FakeEmailSender()
        fake.send_otp(email="a@b.com", code="123456", purpose="login")
        assert fake.last_code("a@b.com", "login") == "123456"


# ===========================================================================
# SmtpEmailSender — message structure
# ===========================================================================

class TestSmtpEmailSenderMessage:
    """Patching ``smtplib.SMTP`` to capture the sent ``EmailMessage``."""

    def _send(
        self,
        mock_smtp_cls: MagicMock,
        *,
        settings: SmtpSettings | None = None,
        code: str = "654321",
        purpose: str = "login",
        ttl_seconds: int | None = None,
    ) -> EmailMessage:
        """Invoke send_otp with a patched SMTP and return the captured message."""
        s = settings or _smtp_settings()
        sender = SmtpEmailSender(settings=s)
        sender.send_otp(
            email="user@test.com",
            code=code,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
        )
        ctx = mock_smtp_cls.return_value.__enter__.return_value
        assert ctx.send_message.call_count == 1
        captured: EmailMessage = ctx.send_message.call_args[0][0]
        return captured

    def test_from_header_is_from_address(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls, settings=_smtp_settings(from_address="from@example.com"))
        assert msg["From"] == "from@example.com"

    def test_to_header_is_email(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls)
        assert msg["To"] == "user@test.com"

    def test_subject_is_present(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls)
        assert msg["Subject"]  # non-empty

    def test_body_contains_code(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls, code="654321")
        body = msg.get_payload()
        assert "654321" in body

    def test_body_contains_expiry_when_ttl_given(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls, ttl_seconds=600)
        body = str(msg.get_payload())
        # 600s must render deterministically as "10 minutes"
        assert "expires in 10 minutes" in body.lower()

    def test_body_does_not_mention_expiry_when_ttl_absent(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls, ttl_seconds=None)
        body = str(msg.get_payload())
        # Without ttl there must be NO expiry line (guards the conditional branch)
        assert "expires" not in body.lower()

    def test_registration_purpose_affects_body(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            msg = self._send(mock_smtp_cls, purpose="registration")
        body = str(msg.get_payload())
        # Body must include the code AND be phrased for registration
        assert "654321" in body
        assert "registration" in body.lower()

    def test_smtp_context_manager_is_used(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            settings = _smtp_settings()
            sender = SmtpEmailSender(settings=settings)
            sender.send_otp(email="u@example.com", code="000000", purpose="login")
        mock_smtp_cls.assert_called_once_with(settings.host, settings.port)


# ===========================================================================
# SmtpEmailSender — STARTTLS / login control
# ===========================================================================

class TestSmtpEmailSenderTlsAndLogin:
    """starttls and login are called or skipped based on settings."""

    def _ctx(self, mock_smtp_cls: MagicMock) -> MagicMock:
        return mock_smtp_cls.return_value.__enter__.return_value

    def test_starttls_called_when_use_tls_true(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            sender = SmtpEmailSender(settings=_smtp_settings(use_tls=True))
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).starttls.assert_called_once()

    def test_starttls_not_called_when_use_tls_false(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            sender = SmtpEmailSender(settings=_smtp_settings(use_tls=False))
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).starttls.assert_not_called()

    def test_login_called_when_credentials_present(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            settings = _smtp_settings(username="user@smtp.com", password="pass123")
            sender = SmtpEmailSender(settings=settings)
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).login.assert_called_once_with("user@smtp.com", "pass123")

    def test_login_not_called_when_username_empty(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            sender = SmtpEmailSender(settings=_smtp_settings(username="", password="pass"))
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).login.assert_not_called()

    def test_login_not_called_when_password_empty(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            sender = SmtpEmailSender(settings=_smtp_settings(username="user", password=""))
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).login.assert_not_called()

    def test_login_not_called_when_both_empty(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            sender = SmtpEmailSender(settings=_smtp_settings(username="", password=""))
            sender.send_otp(email="u@e.com", code="111111", purpose="login")
        self._ctx(mock_smtp_cls).login.assert_not_called()


# ===========================================================================
# Security regression — no code / no raw email in logs
# ===========================================================================

class TestSmtpEmailSenderLogSafety:
    """The module logger must never emit the raw email or the OTP code."""

    def test_code_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with patch("smtplib.SMTP"):
            sender = SmtpEmailSender(settings=_smtp_settings())
            with caplog.at_level(logging.DEBUG, logger="openwellness_api.auth.email_sender"):
                sender.send_otp(
                    email="secure@example.com",
                    code="SECRET9",
                    purpose="login",
                )
        assert "SECRET9" not in caplog.text

    def test_raw_email_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with patch("smtplib.SMTP"):
            sender = SmtpEmailSender(settings=_smtp_settings())
            with caplog.at_level(logging.DEBUG, logger="openwellness_api.auth.email_sender"):
                sender.send_otp(
                    email="secure@example.com",
                    code="SECRET9",
                    purpose="login",
                )
        assert "secure@example.com" not in caplog.text

    def test_sha256_of_email_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        email = "secure@example.com"
        with patch("smtplib.SMTP"):
            sender = SmtpEmailSender(settings=_smtp_settings())
            with caplog.at_level(logging.DEBUG, logger="openwellness_api.auth.email_sender"):
                sender.send_otp(email=email, code="SECRET9", purpose="login")
        expected_hash = _sha256(email)
        assert expected_hash in caplog.text

    def test_no_leak_on_smtp_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Even when SMTP fails, the failure path must not log the code/raw email."""
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__.side_effect = OSError("boom")
            sender = SmtpEmailSender(settings=_smtp_settings())
            with caplog.at_level(logging.DEBUG, logger="openwellness_api.auth.email_sender"):
                with pytest.raises(OSError):
                    sender.send_otp(
                        email="secure@example.com",
                        code="SECRET9",
                        purpose="login",
                    )
        assert "SECRET9" not in caplog.text
        assert "secure@example.com" not in caplog.text


# ===========================================================================
# Protocol conformance
# ===========================================================================

def _accept_email_sender(sender: EmailSender) -> str:
    """Function typed to accept any ``EmailSender`` — used as a conformance check."""
    return type(sender).__name__


class TestProtocolConformance:
    """Both implementations satisfy the ``EmailSender`` protocol."""

    def test_smtp_sender_satisfies_protocol(self) -> None:
        sender = SmtpEmailSender(settings=_smtp_settings())
        result = _accept_email_sender(sender)
        assert result == "SmtpEmailSender"

    def test_fake_sender_satisfies_protocol(self) -> None:
        sender = FakeEmailSender()
        result = _accept_email_sender(sender)
        assert result == "FakeEmailSender"

    def test_smtp_sender_is_runtime_checkable(self) -> None:
        sender = SmtpEmailSender(settings=_smtp_settings())
        assert isinstance(sender, EmailSender)

    def test_fake_sender_is_runtime_checkable(self) -> None:
        sender = FakeEmailSender()
        assert isinstance(sender, EmailSender)
