"""MDBCollectionRepository construction against the narrow MongoConfig protocol."""

from dataclasses import dataclass

from openwellness_core.infrastructure.drivers.mdb_collection_repository import (
    MDBCollectionRepository,
)


@dataclass
class FakeMongoConfig:
    url: str
    db: str

    def get_url(self) -> str:
        return self.url


def test_constructs_from_narrow_mongo_protocol_only():
    mongo = FakeMongoConfig(url="mongodb://localhost:27017", db="testdb")

    repo = MDBCollectionRepository(mongo=mongo)

    assert repo.db.name == "testdb"
