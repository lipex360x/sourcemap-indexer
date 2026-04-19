# sourcemap-indexer

Index any codebase into SQLite and enrich file metadata via an LLM (any OpenAI-compatible endpoint).

The goal: let an AI assistant understand large codebases through SQL queries instead of reading every file.

## Installation

```bash
uv tool install "git+https://github.com/lipex360x/sourcemap-indexer.git@main"
```

## Quickstart

```bash
cd <your-project>
sourcemap init    # create .docs/maps/, .sourcemapignore, index.db
sourcemap walk    # scan files and sync into SQLite
sourcemap enrich  # call LLM to annotate each file
sourcemap stats   # overview: total, enriched, pending
```

## Commands

### Setup

| Command | Description |
|---------|-------------|
| `sourcemap init` | Create `.docs/maps/`, `.sourcemapignore`, and `index.db` |
| `sourcemap walk` | Scan files and sync metadata into SQLite in one step |

### Enrichment

| Command | Description |
|---------|-------------|
| `sourcemap enrich [--limit N]` | Send pending files to the LLM (validates reachability first) |
| `sourcemap stale` | List files whose content changed since the last enrich run |

### Exploration

| Command | Description |
|---------|-------------|
| `sourcemap stats` | Total, enriched, and pending counts by layer and language |
| `sourcemap overview` | Layer × language matrix |
| `sourcemap domain` | Enriched domain-layer files with their purpose |
| `sourcemap effects` | Files with network or git side effects |
| `sourcemap tags` | Top 30 semantic tags by frequency |
| `sourcemap unstable` | Experimental or deprecated files |
| `sourcemap find [--tag T] [--layer L] [--language L]` | Search by tag, layer, or language |
| `sourcemap show <path>` | Full metadata for a specific file |
| `sourcemap query "<sql>"` | Free-form SQL against the index database |

### Maintenance

| Command | Description |
|---------|-------------|
| `sourcemap reset` | Delete the index (offers a timestamped backup before wiping) |
| `sourcemap restore` | Restore `index.db` from a previously saved `.bak` file |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCEMAP_LLM_URL` | `http://localhost:1234/v1/chat/completions` | LLM endpoint |
| `SOURCEMAP_LLM_MODEL` | `qwen/qwen3-coder-30b` | Model name |

## Ignoring files

`sourcemap init` creates a default `.sourcemapignore`. Files matched by `.gitignore` are also skipped automatically.

Add project-specific patterns using the same syntax as `.gitignore`:

```
.venv/
dist/
*.min.js
secrets/
```

## Plugging in a different LLM

The enrichment client targets any OpenAI-compatible endpoint:

```bash
export SOURCEMAP_LLM_URL=https://api.openai.com/v1/chat/completions
export SOURCEMAP_LLM_MODEL=gpt-4o
sourcemap enrich --limit 10
```

## Post-commit hook (auto-walk on every commit)

```bash
bash scripts/bash/install-hook.sh
```

Installs a `post-commit` hook that runs `sourcemap walk` after every commit, keeping the index current. Enrichment is not automatic — it calls the LLM and can be slow.

## SQLite schema

```sql
items        (id, path, name, language, layer, stability, purpose,
              lines, size_bytes, content_hash, llm_hash,
              needs_llm, deleted_at, created_at, updated_at, llm_at)
tags         (item_id, tag)
side_effects (item_id, effect)
invariants   (item_id, invariant)
```

Layers: `domain | infra | application | cli | hook | lib | config | doc | test | unknown`

## Dev setup

```bash
git clone https://github.com/lipex360x/sourcemap-indexer.git
cd sourcemap-indexer
uv sync
uv run pytest
```
