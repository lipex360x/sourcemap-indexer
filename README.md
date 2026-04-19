# sourcemap-indexer

Python library that indexes any codebase into SQLite and enriches file metadata via a local LLM (OpenAI-compatible endpoint, e.g. LM Studio + qwen3-coder-30b).

The goal: let Claude understand large codebases through SQL queries instead of reading every file.

## Installation

```bash
pip install git+https://github.com/lipex360/sourcemap-indexer.git
```

## Dev setup

```bash
git clone https://github.com/lipex360/sourcemap-indexer.git
cd sourcemap-indexer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Quickstart

```bash
cd <your-project>
sourcemap init                    # creates .docs/maps/, .sourcemapignore, index.db
sourcemap walk                    # walks files → .docs/maps/index.yaml
sourcemap sync                    # loads YAML into SQLite
sourcemap enrich                  # calls local LLM to annotate files (needs LM Studio)
sourcemap stats                   # overview: total, enriched, pending
```

## Commands

| Command | Description |
|---------|-------------|
| `sourcemap init` | Initialize index in current project |
| `sourcemap walk` | Scan files, write `index.yaml` |
| `sourcemap sync` | Sync YAML into SQLite (insert / update / soft-delete) |
| `sourcemap enrich [--limit N]` | Enrich pending files via LLM |
| `sourcemap find [--tag T] [--layer L] [--language L]` | Search indexed files |
| `sourcemap show <path>` | Show full metadata for a file |
| `sourcemap stats` | Counts by layer and language |
| `sourcemap stale` | List files changed since last enrich |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCEMAP_LLM_URL` | `http://localhost:1234/v1/chat/completions` | LLM endpoint |
| `SOURCEMAP_LLM_MODEL` | `qwen/qwen3-coder-30b` | Model name |

## Post-commit hook (auto-sync on every commit)

```bash
bash scripts/bash/install-hook.sh
```

This installs a `post-commit` hook that runs `sourcemap walk && sourcemap sync` after every commit, keeping the index current. Enrichment is not automatic (it calls the LLM and can be slow).

## Ignoring files

Create `.sourcemapignore` in your project root (same syntax as `.gitignore`):

```
.venv/
dist/
*.min.js
secrets/
```

`sourcemap init` creates a sensible default automatically.

## SQLite schema (quick reference)

```sql
SELECT path, language, layer, stability, purpose FROM items
WHERE needs_llm = 0
ORDER BY layer, path;

SELECT i.path, t.name FROM items i
JOIN tags t ON t.item_id = i.id
WHERE t.name = 'authentication';
```

Tables: `items`, `tags`, `side_effects`, `invariants`.

## Plugging in a different LLM

The enrichment client targets any OpenAI-compatible endpoint. Point it at Claude, GPT-4, or any other provider:

```bash
export SOURCEMAP_LLM_URL=https://api.anthropic.com/v1/chat/completions
export SOURCEMAP_LLM_MODEL=claude-opus-4-7-20251101
sourcemap enrich --limit 10
```

## Example workflow with LM Studio

1. Download [LM Studio](https://lmstudio.ai) and load `qwen/qwen3-coder-30b`
2. Start the local server (default port 1234)
3. Run `sourcemap enrich --limit 20` to annotate the first batch
4. Run `sourcemap find --layer domain` to explore what was indexed
