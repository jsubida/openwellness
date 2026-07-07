"""CBEntityRepository construction against the narrow Couchbase/SyncGateway protocols."""

from dataclasses import dataclass

from openwellness_core.infrastructure.drivers.cb_entity_repository import (
    CBEntityRepository,
)


@dataclass
class FakeCouchbaseConfig:
    url: str
    username: str
    password: str
    bucket_name: str


@dataclass
class FakeSyncGatewayConfig:
    url: str

    def get_url(self) -> str:
        return self.url


def test_constructs_from_narrow_protocols_only():
    CBEntityRepository._instance = None

    couchbase = FakeCouchbaseConfig(
        url="couchbase://example",
        username="user",
        password="pass",
        bucket_name="bucket",
    )
    sync_gateway = FakeSyncGatewayConfig(url="http://example/sg")

    repo = CBEntityRepository(couchbase=couchbase, sync_gateway=sync_gateway)

    assert repo.connection_string == "couchbase://example"
    assert repo.username == "user"
    assert repo.password == "pass"
    assert repo.bucket_name == "bucket"
    assert repo.sync_gateway_url == "http://example/sg"

    CBEntityRepository._instance = None
