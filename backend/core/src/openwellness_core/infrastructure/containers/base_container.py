"""Composition root for any openwellness consumer.

Concrete services (API, scheduler, worker) subclass and supply the
``app_config`` provider; subclasses don't need to redeclare entities or
repositories.
"""

from ..config.app_config import AppConfigInterface
from .entity_container import EntityContainer
from .providers import DeclarativeContainer, DIContainer, DIDependency
from .repository_container import RepositoryContainer


class BaseContainer(DeclarativeContainer):
    """Wires the entity + repository sub-containers."""

    app_config = DIDependency(instance_of=AppConfigInterface)
    entities = DIContainer(EntityContainer)
    repositories = DIContainer(
        RepositoryContainer,
        app_config=app_config,
        entities=entities,
    )
