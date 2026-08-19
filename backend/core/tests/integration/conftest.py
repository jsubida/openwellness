"""Fixtures binding the integration suite to the live Sync Gateway harness.

These fixtures do NOT start anything. They bind to the `couchbase`,
`couchbase-init` and `sync-gateway` services declared in this repo's own
`docker-compose.yml`, at the versions production runs (Sync Gateway 2.8.2 CE,
Couchbase Server 6.6 CE). Start the harness with::

    ./scripts/render_sync_gateway_config.sh
    docker compose up -d couchbase couchbase-init sync-gateway

When the harness is absent every test that depends on these fixtures skips,
with a message naming the URL that was tried and the command above — a skip
whose message does not say how to un-skip it is how a permanently-skipped
suite goes unnoticed.

Two interfaces are in play and the split is the whole point of the suite:

* the **admin** interface (`:4985`) is unauthenticated and bypasses channel
  authorization entirely. The application's Couchbase driver sends no
  credentials, and GUEST is disabled to match production, so the driver binds
  here — as the deployed services do.
* the **public** interface (`:4984`) is the channel-authorization boundary.
  The proof this suite exists to produce is a read *through this interface, as
  an authenticated non-owner subscriber*. An admin read would pass even if
  every subscriber on earth had lost access, so it can never be the primary
  measurement.

Sync Gateway admin REST endpoints used here:

* ``PUT  {admin}/{db}/_user/{name}``  — provision a user with ``admin_channels``
* ``DELETE {admin}/{db}/_user/{name}`` — remove it
* ``GET  {admin}/{db}/{doc_id}``       — read a document's current revision
* ``DELETE {admin}/{db}/{doc_id}?rev=`` — tombstone a document during cleanup
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Callable, Iterator

import pytest
import requests

# Short on purpose: the reachability probe is a gate, not a wait. A harness
# that needs longer than this to answer its own root is not up yet, and a test
# run that blocks on it looks like a hang rather than a missing service.
_PROBE_TIMEOUT_SECONDS = 3.0

# Long enough for a Couchbase-backed write under amd64 emulation.
_REQUEST_TIMEOUT_SECONDS = 15.0

_START_HARNESS = (
    "./scripts/render_sync_gateway_config.sh && "
    "docker compose up -d couchbase couchbase-init sync-gateway"
)


@dataclass(frozen=True)
class SGHarness:
    """Resolved endpoints of the running Sync Gateway harness."""

    public_url: str
    admin_url: str
    db: str

    @property
    def public_db_url(self) -> str:
        """The channel-authorization boundary — reads by real users."""
        return f"{self.public_url}/{self.db}"

    @property
    def admin_db_url(self) -> str:
        """The unauthenticated interface the application driver binds to."""
        return f"{self.admin_url}/{self.db}"


@dataclass(frozen=True)
class SGUser:
    """A Sync Gateway user provisioned for the duration of one test."""

    name: str
    password: str
    channel: str

    @property
    def auth(self) -> tuple[str, str]:
        return (self.name, self.password)


@dataclass
class _HarnessCouchbaseConfig:
    """Satisfies :class:`CouchbaseConfig` without the app container.

    Only consumed if a test reaches the N1QL cluster client; the Sync Gateway
    HTTP path this suite exercises never touches it, and the driver connects
    lazily, so an unreachable cluster here costs nothing.
    """

    url: str
    username: str
    password: str
    bucket_name: str


@dataclass
class _HarnessSyncGatewayConfig:
    """Satisfies :class:`SyncGatewayConfig` without the app container."""

    url: str

    def get_url(self) -> str:
        return self.url


def _env_endpoints() -> SGHarness:
    """Resolve harness endpoints, defaulting to the 08-03 compose values.

    Read from the environment so a developer running the harness on
    non-default ports is not blocked by a hardcoded localhost.
    """
    db = os.environ.get("SYNC_GATEWAY_DB") or "spring"
    public = os.environ.get("SYNC_GATEWAY_PUBLIC_URL") or "http://localhost:4984"
    admin = os.environ.get("SYNC_GATEWAY_ADMIN_URL") or "http://localhost:4985"
    return SGHarness(
        public_url=public.rstrip("/"), admin_url=admin.rstrip("/"), db=db
    )


@pytest.fixture(scope="session")
def sg_harness() -> SGHarness:
    """Gate the suite on the harness actually being there, in two stages.

    Stage 1 is the optional dependency: the Couchbase SDK is what the driver
    module imports at import time, and it is absent from a bare install.
    Stage 2 is reachability. Both stages skip rather than fail — an absent
    harness is an environment fact, not a defect in the code under test.
    """
    try:
        import couchbase  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"the Couchbase SDK is not installed: {exc}")

    harness = _env_endpoints()
    for label, url in (
        ("public", f"{harness.public_url}/"),
        ("admin", f"{harness.admin_db_url}/"),
    ):
        try:
            response = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
        except requests.RequestException as exc:  # pragma: no cover - env
            pytest.skip(
                f"Sync Gateway {label} interface not reachable at {url} "
                f"({exc.__class__.__name__}). Start the harness with: "
                f"{_START_HARNESS}"
            )
        if response.status_code >= 500:  # pragma: no cover - env
            pytest.skip(
                f"Sync Gateway {label} interface answered {response.status_code} "
                f"at {url}; the harness is up but not serving. Restart it with: "
                f"{_START_HARNESS}"
            )
    return harness


@pytest.fixture()
def cb_driver(sg_harness: SGHarness):
    """A ``CBEntityRepository`` bound to the live harness admin interface.

    The driver enforces a process-wide singleton in ``__new__``, so a second
    construction with different settings silently returns the first instance.
    That failure surfaces as a Sync Gateway problem — writes landing in a
    database nobody configured — rather than as the fixture bug it is, so the
    singleton is reset here before and after rather than trusted to match.
    """
    from openwellness_core.infrastructure.drivers.cb_entity_repository import (
        CBEntityRepository,
    )

    CBEntityRepository._instance = None
    driver = CBEntityRepository(
        couchbase=_HarnessCouchbaseConfig(
            url=os.environ.get("COUCHBASE_URL") or "couchbase://localhost",
            username=os.environ.get("COUCHBASE_ADMIN_USER") or "Administrator",
            password=os.environ.get("COUCHBASE_ADMIN_PASSWORD") or "",
            bucket_name=os.environ.get("COUCHBASE_BUCKET_NAME") or sg_harness.db,
        ),
        # The application driver authenticates with nothing, and GUEST is
        # disabled to match production, so the admin interface is the only one
        # it can use. The public interface is reserved for `read_as_user`.
        sync_gateway=_HarnessSyncGatewayConfig(url=sg_harness.admin_db_url),
    )
    try:
        yield driver
    finally:
        CBEntityRepository._instance = None


@pytest.fixture()
def repo_factory(cb_driver) -> Callable[..., object]:
    """Build a ``CBBaseRepository`` for an entity/persistence pair.

    Keeps the wiring in one place so a parameterized test names only the two
    classes under test.
    """
    from openwellness_core.adapters.couchbase.repositories.cb_base_repository import (
        CBBaseRepository,
    )

    def _factory(entity_type, persistence_type):
        return CBBaseRepository(
            repo=cb_driver,
            entity_type=entity_type,
            persistence_type=persistence_type,
        )

    return _factory


@pytest.fixture()
def sg_subscriber(sg_harness: SGHarness) -> Iterator[SGUser]:
    """Provision a Sync Gateway user subscribed to one generated channel.

    This user is deliberately **not** any test document's owner: the sync
    function grants ``doc.owner`` unconditionally, so an owner's read proves
    nothing about the channel array. Access via the channel alone is the
    single-interpretation measurement (D-18).

    The password is generated per test and never written to disk.
    """
    suffix = uuid.uuid4().hex[:12]
    user = SGUser(
        name=f"sub_{suffix}",
        password=uuid.uuid4().hex,
        channel=f"itest:{suffix}",
    )
    response = requests.put(
        f"{sg_harness.admin_db_url}/_user/{user.name}",
        json={
            "name": user.name,
            "password": user.password,
            "admin_channels": [user.channel],
        },
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    assert response.status_code in (200, 201), (
        f"could not provision subscriber {user.name}: "
        f"{response.status_code} {response.text}"
    )
    try:
        yield user
    finally:
        requests.delete(
            f"{sg_harness.admin_db_url}/_user/{user.name}",
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )


@pytest.fixture()
def sg_documents(sg_harness: SGHarness) -> Iterator[Callable[[str], str]]:
    """Register document ids for removal at the end of the test.

    The harness volume is persistent, so without this a re-run accumulates
    documents and collides on ids that a test computes rather than generates.
    Registration is explicit and idempotent; teardown tolerates a document
    that is already gone.
    """
    registered: list[str] = []

    def _register(doc_id: str) -> str:
        if doc_id not in registered:
            registered.append(doc_id)
        return doc_id

    try:
        yield _register
    finally:
        for doc_id in registered:
            current = requests.get(
                f"{sg_harness.admin_db_url}/{doc_id}",
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            if current.status_code != 200:
                continue
            rev = current.json().get("_rev", "")
            requests.delete(
                f"{sg_harness.admin_db_url}/{doc_id}?rev={rev}",
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )


@pytest.fixture()
def read_as_user(
    sg_harness: SGHarness,
) -> Callable[[SGUser, str], requests.Response]:
    """Read a document as ``user`` through the public interface.

    Returns the :class:`requests.Response`, never a boolean. Sync Gateway
    answers a read the caller has no channel for with 403 on this path but
    404 on others, and both mean "cannot see it"; handing back the response
    makes each test state which answer it accepts and why, instead of burying
    that judgement in a helper.
    """

    def _read(user: SGUser, doc_id: str) -> requests.Response:
        return requests.get(
            f"{sg_harness.public_db_url}/{doc_id}",
            auth=user.auth,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )

    return _read


@pytest.fixture()
def admin_read(sg_harness: SGHarness) -> Callable[[str], requests.Response]:
    """Read a document through the admin interface, bypassing authorization.

    Used only for *secondary* assertions about a document's stored body — the
    channels array it carries, its revision, its audit field. It can never be
    the proof that a subscriber retained access, because it answers 200 for a
    document every subscriber has lost.
    """

    def _read(doc_id: str) -> requests.Response:
        return requests.get(
            f"{sg_harness.admin_db_url}/{doc_id}",
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )

    return _read
