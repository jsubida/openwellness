"""Re-export aliases for ``dependency_injector`` providers.

Centralizing these as short, project-flavored names keeps the container
declarations terse and lets us swap the backing library without touching
every container.
"""

from dependency_injector import containers, providers

DIContainer = providers.Container
DICallable = providers.Callable
DIDelegatedCallable = providers.DelegatedCallable
DIDependenciesContainer = providers.DependenciesContainer
DIDependency = providers.Dependency
DIFactory = providers.Factory
DIObject = providers.Object
DIProvider = providers.Provider
DISingleton = providers.Singleton

DeclarativeContainer = containers.DeclarativeContainer

__all__ = [
    "DICallable",
    "DIContainer",
    "DIDelegatedCallable",
    "DIDependenciesContainer",
    "DIDependency",
    "DIFactory",
    "DIObject",
    "DIProvider",
    "DISingleton",
    "DeclarativeContainer",
]
