# core

`openwellness-core` — the shared Python package that holds the platform's
domain models, repository interfaces, persistence adapters (Couchbase +
Mongo), the driver clients those adapters depend on, and the
dependency-injection wiring that assembles them.

It is a library: it carries no service entry point of its own and is
consumed by importing `openwellness_core`.

## Architecture

The package is organized after **Robert C. Martin's (Uncle Bob's) Clean
Architecture**. Code is split into concentric layers, and the
[Dependency Rule](#dependency-rule) is absolute: **source-code dependencies
only ever point inward.** An inner layer never knows anything about an outer
one. Linked terms below are defined in the [Glossary](#glossary).

```text
        ┌───────────────────────────────────────────────────┐
        │ infrastructure/        Frameworks & Drivers       │
        │   drivers, config, containers                     │
        │   ┌────────────────────────────────────────────┐  │
        │   │ adapters/          Interface Adapters      │  │
        │   │   couchbase/, mongo/, interfaces/          │  │
        │   │   ┌─────────────────────────────────────┐  │  │
        │   │   │ application/   Use-Case Boundaries  │  │  │
        │   │   │   repositories/, dtos/              │  │  │
        │   │   │   ┌─────────────────────────────┐   │  │  │
        │   │   │   │ domain/      Entities       │   │  │  │
        │   │   │   │  models, value_objects,     │   │  │  │
        │   │   │   │  exceptions                 │   │  │  │
        │   │   │   └─────────────────────────────┘   │  │  │
        │   │   └─────────────────────────────────────┘  │  │
        │   └────────────────────────────────────────────┘  │
        └───────────────────────────────────────────────────┘
                    dependencies point inward ──►
```

### Layers

- **`domain/` — Enterprise business rules ([Entities](#entities), innermost).**
  Pure Python dataclasses, immutable `value_objects/`, and `exceptions/`. No framework
  imports, no persistence opinions. This layer imports _nothing_ from the
  others and is the import root for everything else.

- **`application/` — Application business rules ([Use Cases](#use-cases)).**
  Abstract repository interfaces (the [_ports_](#port)), DTOs (`dtos/`) and
  application-level `exceptions`. Depends only on `domain/`. Persistence-only
  concerns like `archive`/`unarchive` are declared here as repository
  contracts, never on the domain entities.

- **`adapters/` — [Interface Adapters](#interface-adapters).**
  Concrete implementations of the application ports, one subtree per backing
  store:
  - `couchbase/` — repositories backed by Couchbase / Sync Gateway.
  - `mongo/` — repositories backed by MongoDB.

  Each subtree pairs a `repositories/` package (the port implementations)
  with a `model/` package of **network model classes** (Pydantic models). The
  network model classes own all wire-format concerns and map across the
  boundary via `from_domain()` / `to_domain()`, so a domain object never
  leaks storage details and storage rows never leak into the domain.

- **`infrastructure/` — [Frameworks & Drivers](#frameworks--drivers) (outermost).**
  - `drivers/` — the concrete clients: `CBEntityRepository` (Sync Gateway
    HTTP + N1QL through the Couchbase SDK) and `MDBCollectionRepository`
    (a `pymongo` wrapper).
  - `interfaces/` — low-level driver ports the adapters depend on
    (`EntityRepository`, `CollectionRepository`) plus their result types.
  - `config/` — `AppConfigInterface`, the minimal config slice (Couchbase,
    Sync Gateway, Mongo) each service extends with its own keys.
  - `containers/` — the dependency-injection composition root, built on
    [`dependency-injector`](https://python-dependency-injector.ets-labs.org/).
    `BaseContainer` wires `EntityContainer` (one provider per domain entity)
    and `RepositoryContainer` (one provider per repository). A service
    subclasses `BaseContainer` and supplies its own `app_config`; per-study
    customizations override a single provider without redeclaring the graph.

### Layout

```text
src/openwellness_core/
├── domain/
│   ├── models/         # BaseEntity, BaseOwnerEntity + subclasses
│   ├── value_objects/  # immutable values (date ranges, weight deltas, …)
│   └── exceptions/     # domain-specific exceptions
├── application/
│   ├── repositories/   # abstract repository interfaces (ports)
│   ├── dtos/           # data-transfer objects
│   └── exceptions.py
├── adapters/
│   ├── couchbase/
│   │   ├── model/          # CB persistence classes + from_domain/to_domain
│   │   └── repositories/   # CB port implementations
│   └── mongo/
│       ├── model/          # Mongo persistence classes + mappers
│       └── repositories/   # Mongo port implementations
└── infrastructure/
    ├── drivers/        # Couchbase (Sync Gateway + N1QL) & Mongo clients
    ├── interfaces/     # low-level driver ports + result types
    ├── config/         # AppConfigInterface
    └── containers/     # dependency-injection composition root
```

## Prerequisites

- **Python 3.12+** (the package targets `>=3.12`).
- **[uv](https://docs.astral.sh/uv/)** for dependency management and running
  commands. `core` is a member of the `backend/` uv workspace.
- Running the _tests_ needs no live Couchbase or Mongo — they exercise the
  mappers and query builders against in-memory fakes. Live credentials
  (see `../../.env.example`) are only needed when a consuming service talks
  to the real datastores.

## Setup

From `backend/` (the workspace root), sync the environment. Pass
`--extra dev` so the test and type-check tools (`pytest`, `pyright`,
declared under `[project.optional-dependencies]`) land in the shared
workspace venv — a plain `uv sync` omits them, and `uv run pytest` then
fails to resolve `openwellness_core`:

```bash
cd backend
uv sync --extra dev
```

`core` installs as an editable package, so `import openwellness_core` works
from the test suite and any consumer without a rebuild.

## Testing

Run the suite from this directory with uv (after the `uv sync --extra dev`
above — without the `dev` extra, `pytest` is not installed):

```bash
cd backend/core
uv run pytest
```

If a run reports `No module named 'pytest'` or `No module named
'openwellness_core'`, the environment was synced without `--extra dev`; rerun
`uv sync --extra dev` from `backend/`.

The suite has two complementary parts:

- `tests/test_smoke.py` — round-trips representative entities through their
  persistence DTOs (`from_domain → model_dump → model_validate → to_domain`)
  and asserts the layer boundaries hold (e.g. routing fields live on the
  persistence class, not the domain entity).
- `tests/test_repositories_queries.py` — drives every Couchbase repository
  method through a fake driver and asserts each one parameterizes all
  user-supplied values (no injection into N1QL strings) and validates
  ordering arguments against an allowlist.

Type-checking uses pyright (config in `../pyrightconfig.json`):

```bash
cd backend
uv run pyright
```

## Glossary

Clean Architecture terms as Robert C. Martin (Uncle Bob) defines them, with a
note on where each shows up in this package. Listed alphabetically.

### Boundary

A line drawn between two layers, across which the [Dependency Rule](#dependency-rule)
is enforced. Control may flow across a boundary in either direction, but
source-code dependencies always point inward — outward calls are made through
abstractions (see [Dependency Inversion Principle](#dependency-inversion-principle)).
Here, the `from_domain()` / `to_domain()` mappers and the abstract repository
interfaces are the boundary crossings.

### Dependency Inversion Principle

High-level policy must not depend on low-level detail; both depend on
abstractions, and the abstraction is owned by the higher-level (inner) module.
This is the mechanism that lets control flow outward across a
[Boundary](#boundary) while source dependencies still point inward: the
`application/` layer declares a [Port](#port), and the outer `adapters/` layer
implements it.

### Dependency Rule

The overriding rule of Clean Architecture: source-code dependencies may point
only inward, toward higher-level policies. Nothing named in an inner circle —
no function, class, variable, or other entity — may be named by code in an
outer circle. In this package: `domain/` depends on nothing, `application/`
depends only on `domain/`, `adapters/` and `infrastructure/` depend inward, and
never the reverse.

### Entities

The innermost circle: enterprise-wide business rules and the critical business
data they operate on. They embody the most general, highest-level policy and
are the least likely to change when something external (a database, a
framework, the UI) changes. Implemented here as the dataclasses under
`domain/models/` together with `domain/value_objects/`.

### Frameworks & Drivers

The outermost circle: databases, web frameworks, device drivers, and other
external agencies. This is glue code and detail, kept at arm's length so it
stays replaceable. Here it is `infrastructure/drivers/` (the Couchbase SDK /
Sync Gateway and `pymongo` clients) and the `dependency-injector`-based
`infrastructure/containers/`.

### Interface Adapters

The circle that converts data between the form most convenient for the
[Use Cases](#use-cases) and [Entities](#entities) and the form most convenient
for an external agency such as a database. Gateways/repositories,
controllers, and presenters live here. In this package it is `adapters/`: the
concrete repositories plus the persistence/network model classes that map to
and from each store's wire format.

### Port

An abstract interface, owned and defined by an inner layer, through which it is
invoked or through which it reaches outward — the inner layer states _what_ it
needs without binding to a concrete _how_. (The term comes from the Ports &
Adapters / Hexagonal style that Clean Architecture absorbs.) The abstract
repository classes in `application/repositories/` and the driver interfaces in
`infrastructure/interfaces/` are the ports of this package.

### Use Cases

The circle just outside the entities: application-specific business rules. A
use case orchestrates the flow of data to and from the entities to accomplish
one operation the system offers. Changes to use cases do not affect entities,
and changes to outer concerns (database, UI) do not affect use cases. Here this
layer is `application/` — the repository contracts and DTOs that the services
program against.
