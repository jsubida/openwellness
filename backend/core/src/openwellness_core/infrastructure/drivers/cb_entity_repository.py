"""Couchbase entity repository (Sync Gateway HTTP client + N1QL via SDK)."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

import requests
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster

from ...adapters.exceptions import RevisionConflictError
from ...adapters.interfaces.entity_repository import EntityRepository
from ...domain.exceptions.domain_exception import NotFound
from ..config.app_config import CouchbaseConfig, SyncGatewayConfig

# HTTP status Sync Gateway answers a stale-revision write with.
_HTTP_CONFLICT = 409

# The `error` value Sync Gateway puts in a conflict response body. Checked
# independently of the status code: 2.8 is the only authority on which of the
# two signals it sets for a given rejection, and depending on one alone turns
# a version quirk into an untyped exception at exactly the moment a caller
# most needs to tell a conflict apart from everything else.
_CONFLICT_ERROR = "conflict"


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
        # Captured before `_sanitize` removes it, purely so a rejection can
        # name the document it was about.
        doc_id = obj.get("id", "") or ""
        obj = self._sanitize(obj)
        response = requests.post(url, json=obj, headers=headers, timeout=10)
        content = response.json()
        # A create carries no revision, so `sent_rev` stays empty.
        return self._process_response(
            obj, content, response.status_code, doc_id=doc_id
        )

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
        """Update a document by its ID, recording ``actor`` as the writer.

        The revision travels to Sync Gateway as the ``?rev=`` query
        parameter, never in the body (see :meth:`_sanitize`). When ``_rev``
        is empty no revision is sent at all, which Sync Gateway accepts only
        if no document exists at ``doc_id``; against an existing document it
        answers with a conflict. Before 08-04 the read path dropped ``_rev``,
        so *every* update took the empty-revision branch — the reason the
        previous docstring described this method as "creates with the given
        ID". That description no longer fits: a document loaded through the
        repository now carries its revision, so the empty case means a
        genuinely new document.

        A rejected revision raises
        :class:`~openwellness_core.adapters.exceptions.RevisionConflictError`
        and the call stops there. This adapter never re-sends the write on
        its own and never merges: re-sending the same body under the current
        revision would overwrite whatever change caused the rejection, which
        is precisely the data loss this phase exists to prevent (D-20). A
        caller wanting that behavior re-reads the document, re-applies its
        change to the fresh state, and calls again — wrapping this error
        itself.
        """
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
            # `rev` is the local captured above, not `obj["_rev"]`: the body
            # no longer carries it by this point.
            return self._process_response(
                obj,
                content,
                response.status_code,
                doc_id=doc_id,
                sent_rev=rev,
            )
        except TypeError as e:
            obj["id"] = doc_id
            obj["_rev"] = rev
            raise e

    def _process_response(
        self,
        obj: dict,
        resp: dict,
        status_code: int,
        doc_id: str = "",
        sent_rev: str = "",
    ) -> dict:
        """Apply a Sync Gateway write response to ``obj``, or raise.

        A stale revision is narrowed out of the generic error path and given
        its own type, because it is the one failure a caller can act on
        differently. Everything else keeps the pre-existing
        :class:`GenericException` behavior.
        """
        if self._is_conflict(resp, status_code):
            raise RevisionConflictError(
                doc_id=doc_id or str(resp.get("id", "")),
                attempted_rev=sent_rev,
                reason=str(resp.get("reason", "")),
            )
        if "id" in resp:
            obj["id"] = resp["id"]
        if "rev" in resp:
            obj["_rev"] = resp["rev"]
        if "error" in resp:
            raise CBEntityRepository.GenericException(
                f"Error: {resp['error']} because {resp['reason']}"
            )
        return obj

    @staticmethod
    def _is_conflict(resp: dict, status_code: int) -> bool:
        """True when the response reports a stale revision, on either signal."""
        if status_code == _HTTP_CONFLICT:
            return True
        return str(resp.get("error", "")).strip().lower() == _CONFLICT_ERROR

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
