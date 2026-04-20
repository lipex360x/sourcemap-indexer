# CLAUDE.md — sourcemap-indexer

## Test runner

```bash
uv run pytest
```

Coverage mínimo: 95%. O pré-commit falha se não atingir.

## Arquitetura em camadas

```
cli.py          → entrada CLI (typer)
application/    → orquestração (walk.py, sync.py, enrich.py)
infra/          → I/O: SQLite, filesystem, LLM client
domain/         → entidades e value objects puros
lib/            → Either monad, logger
```

Application pode importar infra. Domain não importa nada acima de si.

## Convenções de código

Leia `.brain/.docs/references/code-conventions.md` (global) antes de escrever código.

Regras críticas deste projeto:
- Sem comentários em `.py` (exceto shebangs, `# noqa`, `# type: ignore`)
- Sem abreviações banidas: `msg`, `env`, `src`, `exc`, `ctx`, `cfg`, `err`, `buf`, `cmd`, `res`, `tmp`
- Comprimento máximo: 100 chars por linha
- `Either[str, T]` para funções que podem falhar — retorna `left("error-token")` ou `right(value)`
- Logger: `from sourcemap_indexer.lib.log import create_logger`

## Fluxo do comando `walk`

```
CLI walk
  → repo.load_known_files()   ← SELECT do SQLite (mtime, size, lines, hash)
  → run_walk(root, output, known_files)
      → walk_project(root, known_files)   ← fast-path: skip read se mtime+size batem
      → escreve index.yaml
  → run_sync(index.yaml, repo)            ← reconcilia SQLite
```

## Issues planejadas (follow-ups da issue #3)

- `perf(walk): use st_mtime_ns for same-second robustness`
- `perf(walk): replace Path.rglob with os.scandir`
- `refactor: remove index.yaml, SQLite as single source of truth`
- `perf(walk): parallel hashing for large change sets`
