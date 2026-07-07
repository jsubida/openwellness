# Tasks: <feature name>

Rules:

- Tasks are ordered; each leaves the affected package(s) green
  (`cd backend/core && uv run pytest`, `cd backend/api && uv run pytest`,
  `cd backend/scheduler && uv run pytest`, and `cd backend && uv run pyright`
  for the workspace type-check).
- Each task should be completable in one sitting and reference the requirement(s) it serves.
- Check boxes (`[x]`) as tasks complete; add discovered tasks at the point they must run, not at the end.

## Checklist

- [ ] 1. <task> _(Story 1)_
  - <sub-detail if needed: files to touch, tests to write first>
- [ ] 2. <task> _(Story 1)_
- [ ] 3. <task> _(Story 2)_
