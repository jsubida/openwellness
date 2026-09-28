"""SGAdminUserRepository against the real Sync Gateway 2.8.2 harness (HOOK-03).

Proves, against the version production runs, what participant creation relies
on (D-12, D-14):

* ``provision`` creates (201) and is idempotent on repeat (200);
* the admin read shows the granted admin channels;
* the provisioned credentials authenticate on the PUBLIC interface, the one
  devices use (with a wrong-password negative control, so a 200 cannot come
  from GUEST access);
* ``delete`` removes the user, and a second ``delete`` is not an error.

Skips, naming the command that starts the harness, when it is absent.
"""

from __future__ import annotations

import uuid
from typing import Any

import requests
from openwellness_core.infrastructure.drivers.sg_admin_user_repository import (
    SGAdminUserRepository,
)

_TIMEOUT = 15.0


class _StatusRecordingSession(requests.Session):
    """A real session that remembers the status of every response."""

    def __init__(self) -> None:
        super().__init__()
        self.statuses: list[tuple[str, int]] = []

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        response = super().request(method, url, *args, **kwargs)
        self.statuses.append((method, response.status_code))
        return response


def _public_status(harness: Any, name: str, password: str) -> int:
    return requests.get(
        f"{harness.public_db_url}/", auth=(name, password), timeout=_TIMEOUT
    ).status_code


def test_provision_is_idempotent_authenticates_and_deletes(sg_harness: Any):
    name = f"ow1007_{uuid.uuid4().hex[:16]}"
    channels = [name, "study:ow1007itest", "sharedData"]
    session = _StatusRecordingSession()
    repo = SGAdminUserRepository(sg_harness.admin_db_url, session=session, timeout=_TIMEOUT)
    try:
        assert repo.get_by_id(name) is None

        repo.provision(name, name, channels)
        assert session.statuses[-1] == ("PUT", 201), session.statuses

        repo.provision(name, name, channels)
        assert session.statuses[-1] == ("PUT", 200), session.statuses

        user = repo.get_by_id(name)
        assert user is not None
        assert user.name == name
        assert sorted(user.admin_channels) == sorted(channels)
        assert set(channels) <= set(user.all_channels)

        assert _public_status(sg_harness, name, name) == 200
        assert _public_status(sg_harness, name, name + "-wrong") == 401

        repo.delete(name)
        assert session.statuses[-1] == ("DELETE", 200), session.statuses
        assert repo.get_by_id(name) is None
        assert _public_status(sg_harness, name, name) == 401

        repo.delete(name)
        assert session.statuses[-1] == ("DELETE", 404), session.statuses
    finally:
        requests.delete(f"{sg_harness.admin_db_url}/_user/{name}", timeout=_TIMEOUT)
