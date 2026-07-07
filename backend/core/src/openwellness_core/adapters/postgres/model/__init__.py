"""Postgres persistence classes (SQLAlchemy declarative ORM)."""

from .pg_base_entity import Base, PGBaseEntity

__all__ = ["Base", "PGBaseEntity"]
