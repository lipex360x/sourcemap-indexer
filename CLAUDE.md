# CLAUDE.md — sourcemap-indexer

## Local install

The CLI is installed in editable mode — source changes reflect immediately without reinstalling:

```bash
uv tool install --editable .
```

## Development workflow — TDD mandatory

All new behaviour must follow the Red → Green cycle:

1. **RED** — write a failing test that describes the expected behaviour
2. **GREEN** — write the minimum implementation to make it pass
3. Repeat vertically per behaviour (never write all tests then all code)

No implementation without a test first. Pre-commit enforces ≥95% coverage.

## Test runner

```bash
uv run pytest
```

Minimum coverage: 95%. Pre-commit fails if not reached.

## Layer architecture

```
cli.py          → CLI entry point (typer)
application/    → orchestration (walk.py, sync.py, enrich.py)
infra/          → I/O: SQLite, filesystem, LLM client
domain/         → pure entities and value objects
lib/            → Either monad, logger
```

Application may import infra. Domain imports nothing above itself.

## Code conventions

Read `.brain/.docs/references/code-conventions.md` (global) before writing any code.

Critical rules for this project:
- No comments in `.py` (except shebangs, `# noqa`, `# type: ignore`)
- No banned abbreviations: `msg`, `env`, `src`, `exc`, `ctx`, `cfg`, `err`, `buf`, `cmd`, `res`, `tmp`
- Max line length: 100 chars
- `Either[str, T]` for functions that can fail — return `left("error-token")` or `right(value)`
- Logger: `from sourcemap_indexer.lib.log import create_logger`
- `SOURCEMAP_LOG_FILE=1` enables file logging (default off); `SOURCEMAP_DEBUG=1` enables debug level

## Walk command flow

```
CLI walk
  → repo.load_known_files()   ← single SELECT from SQLite (mtime, size, lines, hash)
  → run_walk(root, output, known_files)
      → walk_project(root, known_files)   ← fast-path: skip read_bytes if mtime+size match
      → writes index.yaml
  → run_sync(index.yaml, repo)            ← reconciles SQLite
```

## Planned follow-up issues (from issue #3)

- `perf(walk): use st_mtime_ns for same-second robustness`
- `perf(walk): replace Path.rglob with os.scandir`
- `refactor: remove index.yaml, SQLite as single source of truth`
- `perf(walk): parallel hashing for large change sets`
