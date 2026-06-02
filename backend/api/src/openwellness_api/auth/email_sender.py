"""Email delivery primitives for OTP authentication.

Responsibilities (this module only):
- Define the ``EmailSender`` protocol so callers depend on an abstraction.
- ``SmtpEmailSender``: compose and send a plain-text OTP email via stdlib
  ``smtplib``. No code generation, no Redis/Mongo/HTTP, no background tasks.
- ``FakeEmailSender``: in-memory recorder used in tests and dev; never sends
  real mail and never logs OTP codes.

Security contract
-----------------
The OTP ``code`` and the raw recipient ``email`` MUST NOT appear in any log
line emitted by this module.  The module logger uses only
``sha256(email).hexdigest()`` as the email identifier.
"""

from __future__ import annotations

import hashlib
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

from openwellness_api.config import SmtpSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EmailSender(Protocol):
    """Deliver a one-time password to an email address."""

    def send_otp(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int | None = None,
    ) -> None:
        """Send a plain-text OTP email.

        Parameters
        ----------
        email:
            Recipient address.
        code:
            The 6-digit OTP code (the *caller* generates this).
        purpose:
            ``"login"`` or ``"registration"`` — controls body phrasing.
        ttl_seconds:
            If provided, an expiry line is included in the body
            (e.g. "This code expires in 10 minutes.").
        """
        ...


# ---------------------------------------------------------------------------
# SMTP implementation
# ---------------------------------------------------------------------------

def _build_body(*, code: str, purpose: str, ttl_seconds: int | None) -> str:
    """Compose the plain-text body. ``code`` appears here intentionally."""
    if purpose == "registration":
        action = "complete your registration"
    else:
        action = "log in to your account"

    lines: list[str] = [
        f"Your OpenWellness verification code to {action} is:",
        "",
        f"    {code}",
        "",
    ]

    if ttl_seconds:  # excludes None and a degenerate 0
        minutes, seconds = divmod(ttl_seconds, 60)
        if minutes and seconds:
            human = f"{minutes} minute{'s' if minutes != 1 else ''} and {seconds} second{'s' if seconds != 1 else ''}"
        elif minutes:
            human = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            human = f"{seconds} second{'s' if seconds != 1 else ''}"
        lines.append(f"This code expires in {human}.")
        lines.append("")

    lines += [
        "If you did not request this code, please ignore this email.",
        "",
        "— The OpenWellness Team",
    ]

    return "\n".join(lines)


class SmtpEmailSender:
    """Send OTP emails via SMTP (STARTTLS on port 587).

    All configuration is injected via ``SmtpSettings``; this class never reads
    ``os.environ`` directly and holds no module-level state.
    """

    def __init__(self, *, settings: SmtpSettings) -> None:
        self._settings = settings

    def send_otp(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int | None = None,
    ) -> None:
        s = self._settings

        msg = EmailMessage()
        msg["From"] = s.from_address
        msg["To"] = email
        msg["Subject"] = "Your OpenWellness verification code"
        msg.set_content(_build_body(code=code, purpose=purpose, ttl_seconds=ttl_seconds))

        with smtplib.SMTP(s.host, s.port) as smtp:
            if s.use_tls:
                smtp.starttls()
            if s.username and s.password:
                smtp.login(s.username, s.password)
            smtp.send_message(msg)

        # Log with a safe identifier only — never the raw email or the code.
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        logger.info("OTP email sent: email_sha256=%s purpose=%s", email_hash, purpose)


# ---------------------------------------------------------------------------
# Fake implementation (tests / dev)
# ---------------------------------------------------------------------------


class FakeEmailSender:
    """In-memory OTP email recorder.

    Attributes
    ----------
    sent:
        Ordered list of ``(email, code, purpose)`` tuples, one per
        ``send_otp`` call. Tests read both the list and ``last_code``.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_otp(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int | None = None,
    ) -> None:
        self.sent.append((email, code, purpose))

    def last_code(self, email: str, purpose: str | None = None) -> str | None:
        """Return the most recent code sent to *email*, optionally by *purpose*.

        Returns ``None`` if no matching send has been recorded.
        """
        for e, c, p in reversed(self.sent):
            if e == email and (purpose is None or p == purpose):
                return c
        return None
