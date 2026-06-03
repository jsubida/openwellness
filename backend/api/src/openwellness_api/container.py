"""API composition root.

Subclasses :class:`BaseContainer` solely to mark the API as the binding
site for the concrete ``AppConfig`` — the rest of the graph (entities,
repositories) is inherited unchanged.
"""

from openwellness_core.infrastructure.containers import BaseContainer


class ApplicationContainer(BaseContainer):
    """API composition root; bound to a concrete ``AppConfig`` in the lifespan."""
