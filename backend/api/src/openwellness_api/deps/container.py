"""Container-backed FastAPI dependency factory.

Each repository declared on :class:`RepositoryContainer` is exposed by name;
``container_dep("user")`` returns a FastAPI dep that resolves
``request.app.state.container.repositories.user`` per request. Going through
the request-scoped container instance is what makes
``container.repositories.<name>.override(...)`` visible to live routes —
which is the test override surface.
"""

from typing import Any, Callable

from fastapi import Request


def container_dep(provider_name: str) -> Callable[[Request], Any]:
    """Build a FastAPI dep that pulls a repository from the active container."""

    def _resolve(request: Request) -> Any:
        container = request.app.state.container
        try:
            provider = getattr(container.repositories, provider_name)
        except AttributeError as e:
            raise RuntimeError(
                f"No provider named {provider_name!r} on RepositoryContainer"
            ) from e
        return provider()

    _resolve.__name__ = f"resolve_{provider_name}"
    return _resolve
