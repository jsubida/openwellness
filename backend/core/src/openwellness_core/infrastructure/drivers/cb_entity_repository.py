"""Couchbase entity repository (Sync Gateway HTTP client + N1QL via SDK)."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

import requests
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster

from ...adapters.interfaces.entity_repository import EntityRepository
from ...domain.exceptions.domain_exception import NotFound
from ..config.app_config import CouchbaseConfig, SyncGatewayConfig


class CBEntityRepository(EntityRepository):
    """Couchbase entity repository.

    Reads/writes documents via Sync Gateway HTTP, runs N1QL queries through
    the Couchbase SDK cluster client.
    """

    _instance: CBEntityRepository | None = None
    _initialized = None

    class GenericException(Exception):
        """Generic exception class."""

    def __new__(
        cls, couchbase: CouchbaseConfig, sync_gateway: SyncGatewayConfig
    ) -> CBEntityRepository:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self, couchbase: CouchbaseConfig, sync_gateway: SyncGatewayConfig
    ) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.connection_string = couchbase.url
        self.username = couchbase.username
        self.password = couchbase.password
        self.bucket_name = couchbase.bucket_name
        self.sync_gateway_url = sync_gateway.get_url()
        self._cluster: Cluster | None = None
        self._bucket = None

    def initialize(self) -> None:
        """Initialize the connection to the Couchbase cluster."""
        if self._cluster is None:
            auth = PasswordAuthenticator(self.username, self.password)
            self._cluster = Cluster(self.connection_string, authenticator=auth)
            self._cluster.wait_until_ready(timedelta(seconds=5))
            self._bucket = self._cluster.bucket(self.bucket_name)
            logging.debug(
                "Connected to Couchbase bucket %s; %s",
                self.bucket_name,
                self._bucket.__dict__,
            )

    def cleanup(self) -> None:
        """Close the connection to the Couchbase cluster."""
        if self._cluster is not None:
            self._cluster.close()
            self._cluster = None

    @property
    def bucket(self) -> str:
        return self.bucket_name

    @property
    def cluster(self) -> Cluster:
        if self._cluster is None:
            self.initialize()
        assert self._cluster is not None
        return self._cluster

    def get_by_id(self, doc_id: str) -> dict:
        url = f"{self.sync_gateway_url}/{doc_id}"
        response = requests.get(url, timeout=10)
        doc = response.json()
        if isinstance(doc, str):
            doc = json.loads(doc)
        if "error" in doc:
            raise NotFound(f"{doc_id} {doc['error']} because {doc['reason']}")
        if "_id" in doc:
            doc["id"] = doc.pop("_id")
        return doc

    def get_by_query(
        self, query: str, params: dict | None = None
    ) -> list[dict]:
        if params:
            result = self.cluster.query(query, named_parameters=params)
        else:
            result = self.cluster.query(query)
        return list(result.rows())

    def create(self, obj: dict, *, actor: str) -> dict:
        """Create a document, recording ``actor`` as the writing identity.

        The actor is stamped here as well as in :meth:`update` so a created
        document and a later edit of it agree on who acted. No ``updatedAt``
        stamp is added: the entity already carries one from its domain
        constructor, and a second source of truth for that field would make
        the two disagree.
        """
        url = f"{self.sync_gateway_url}/"
        headers = {"Content-type": "application/json", "Accept": "application/json"}
        obj["updatedBy"] = actor
        obj = self._sanitize(obj)
        response = requests.post(url, json=obj, headers=headers, timeout=10)
        content = response.json()
        return self._process_response(obj, content)

    def execute_query(
        self, query: str, params: dict | None = None
    ) -> list[dict]:
        return self.get_by_query(query, params)

    def delete(self, doc_id: str) -> None:
        doc = self.get_by_id(doc_id)
        rev_id = doc["_rev"]
        url = f"{self.sync_gateway_url}/{doc_id}?rev={rev_id}"
        return requests.delete(url, timeout=10).json()

    def save(self, obj: dict, *, actor: str) -> dict:
        """Dispatch to :meth:`create` or :meth:`update`, threading ``actor``."""
        obj_id = obj.get("id", None)
        if obj_id is None or obj_id == "":
            obj = self._sanitize(obj)
            return self.create(obj, actor=actor)
        return self.update(obj["id"], obj, actor=actor)

    def update(self, doc_id: str, obj: dict, *, actor: str) -> dict:
        """Update a document by its ID, recording ``actor`` as the writer."""
        obj["updatedAt"] = time.time()
        obj["updatedBy"] = actor
        rev = obj["_rev"]
        obj = self._sanitize(obj)
        try:
            url = f"{self.sync_gateway_url}/{doc_id}"
            if rev != "":
                url += f"?rev={rev}"
            headers = {
                "Content-type": "application/json",
                "Accept": "application/json",
            }
            response = requests.put(url, json=obj, headers=headers, timeout=10)
            content = response.json()
            return self._process_response(obj, content)
        except TypeError as e:
            obj["id"] = doc_id
            obj["_rev"] = rev
            raise e

    def _process_response(self, obj: dict, resp: dict) -> dict:
        if "id" in resp:
            obj["id"] = resp["id"]
        if "rev" in resp:
            obj["_rev"] = resp["rev"]
        if "error" in resp:
            raise CBEntityRepository.GenericException(
                f"Error: {resp['error']} because {resp['reason']}"
            )
        return obj

    def _sanitize(self, obj: dict) -> dict:
        # Both keys are removed on purpose: the Sync Gateway REST API takes
        # the document id in the URL path and the revision in the `?rev=`
        # query parameter, never in the request body. A body-borne `_rev` is
        # ignored, so putting it back would silently disable optimistic
        # concurrency. The historical bug was upstream of here — the read
        # path dropped `_rev` entirely, so it was always empty by the time
        # `update` captured it (fixed in 08-04) — not in this removal.
        obj.pop("id", None)
        obj.pop("_rev", None)
        return obj
