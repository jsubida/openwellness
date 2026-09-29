"""Sync Gateway admin-interface client for sync users.

Implements :class:`SyncUserRepository` against Sync Gateway's admin REST
interface (``:4985``), which is unauthenticated and must never be exposed
beyond the application network:

* ``PUT    {admin}/{db}/_user/{name}``  create or update (201 create, 200 update)
* ``GET    {admin}/{db}/_user/{name}``  read (404 when missing)
* ``DELETE {admin}/{db}/_user/{name}``  remove (404 when already gone)

Participant creation (``POST /api/participants``) inserts the participant
(its unique ``_id`` settles a same-id race), then provisions the sync user
before the rest of the Mongo writes (D-12). Credentials keep frame
parity (D-14): name = couchId, password = couchId, admin channels
``[couchId, "study:<studyId>", "sharedData"]``, so fielded app builds keep
syncing. Because the password equals the name in that scheme, this module
puts NEITHER in exception text or log lines: a leaked name is a leaked
password.

Prior-art pitfall: the scheduler's ``HTTPSyncUserRepository`` sends the non-SG
key ``allChannels`` and treats every status but 200 as failure, so a create
(201) would raise. This client sends only keys Sync Gateway defines and
accepts both 200 and 201.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any
from urllib.parse import quote

import requests

from ...application.repositories.sync_user_repository import SyncUserRepository
from ...domain.models.sync_user import SyncUser

_OK_WRITE = (200, 201)
_OK_DELETE = (200, 404)
_REASON_MAX = 200


class SyncUserProvisioningError(Exception):
    """A Sync Gateway admin call on a user failed.

    Carries the operation, the HTTP status (``None`` when no response came
    back) and Sync Gateway's ``reason``. Never the user name or password.
    """

    def __init__(self, operation: str, status: int | None, reason: str) -> None:
        self.operation = operation
        self.status = status
        self.reason = reason
        status_text = "no response" if status is None else f"HTTP {status}"
        super().__init__(f"Sync Gateway user {operation} failed: {status_text} ({reason})")


def _reason(response: requests.Response) -> str:
    """Sync Gateway's ``reason`` field, or ``""``. Never the raw body."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        reason = body.get("reason")
        if isinstance(reason, str):
            return reason[:_REASON_MAX]
    return ""


class SGAdminUserRepository(SyncUserRepository[SyncUser]):
    """Sync users through the Sync Gateway admin interface."""

    def __init__(
        self,
        admin_db_url: str,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base = admin_db_url.rstrip("/")
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout

    def _user_url(self, name: str) -> str:
        return f"{self._base}/_user/{quote(name, safe='')}"

    def _call(self, operation: str, method: str, name: str, **kwargs: Any) -> requests.Response:
        try:
            return self._session.request(
                method, self._user_url(name), timeout=self._timeout, **kwargs
            )
        except requests.RequestException as exc:
            # The exception text of a transport error carries the URL, which
            # carries the name (= the password under D-14). Re-raise with the
            # class name only, and suppress the chained original.
            raise SyncUserProvisioningError(operation, None, exc.__class__.__name__) from None

    def provision(self, name: str, password: str, admin_channels: list[str]) -> bool:
        response = self._call(
            "provision",
            "PUT",
            name,
            json={"name": name, "password": password, "admin_channels": list(admin_channels)},
        )
        if response.status_code not in _OK_WRITE:
            raise SyncUserProvisioningError("provision", response.status_code, _reason(response))
        return response.status_code == 201

    def save(self, user: SyncUser) -> SyncUser:
        response = self._call(
            "save",
            "PUT",
            user.name,
            json={"name": user.name, "admin_channels": list(user.admin_channels)},
        )
        if response.status_code not in _OK_WRITE:
            raise SyncUserProvisioningError("save", response.status_code, _reason(response))
        return user

    def get_by_id(self, entity_id: str) -> SyncUser | None:
        response = self._call("read", "GET", entity_id)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SyncUserProvisioningError("read", response.status_code, _reason(response))
        body = response.json()
        if not isinstance(body, dict):
            raise SyncUserProvisioningError("read", response.status_code, "unexpected body")
        known = {f.name for f in fields(SyncUser)}
        return SyncUser(**{key: value for key, value in body.items() if key in known})

    def delete(self, name: str) -> None:
        response = self._call("delete", "DELETE", name)
        if response.status_code not in _OK_DELETE:
            raise SyncUserProvisioningError("delete", response.status_code, _reason(response))
