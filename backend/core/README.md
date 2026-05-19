# core

Shared Python package imported by `api/` and `scheduler/`.

Contains domain models, repository interfaces, persistence adapters
(Couchbase, Mongo), and the driver clients those adapters depend on.

## Layout

```
src/openwellness_core/
├── domain/
│   ├── models/         # BaseEntity, BaseOwnerEntity + subclasses
│   ├── value_objects/
│   └── exceptions/
├── application/
│   └── repositories/   # repository interfaces (abstract)
├── adapters/
│   ├── couchbase/      # CB repositories, persistence classes, mappers
│   └── mongo/          # Mongo repositories, persistence classes, mappers
└── infrastructure/
    └── drivers/        # Sync Gateway HTTP client, Mongo client wrapper
```

The `domain/` layer is the import root — `application/` and `adapters/` may
import from it, but never the other direction.
