"""Mongo repository for App."""

import os

from ....application.repositories.app_repository import AppRepository
from ....domain.models.app import App
from ...interfaces.collection_repository import CollectionRepository
from ..model.mongo_app import MongoApp
from .mongo_base_repository import MongoBaseRepository


class MongoAppRepository(AppRepository, MongoBaseRepository[App, MongoApp]):
    """Mongo repository for the App entity."""

    def __init__(
        self,
        mongo_repo: CollectionRepository,
        persistence_type: type[MongoApp] = MongoApp,
    ) -> None:
        super().__init__(mongo_repo, App, persistence_type)
        self.entity_type = App

    def create_app(self, name: str, unlistedLink: bool = True) -> App:
        # Deployment-specific identifiers come from the environment (see the
        # repository-root .env.example); unset variables leave the fields None.
        app = App(name=name)
        if unlistedLink:
            app.app_store_id = os.environ.get("APP_STORE_ID")
            app.ios_bundle_id = os.environ.get("APP_IOS_BUNDLE_ID")
            app.one_signal_app_id = os.environ.get("APP_ONE_SIGNAL_APP_ID")
        return self.create(app)
