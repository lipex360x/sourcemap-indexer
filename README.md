<a id="topo"></a>

## sourcemap-indexer

*Index any codebase into SQLite and enrich file metadata via an LLM — so an AI assistant can understand large projects through SQL queries instead of reading every file.*

---

## Index

| # | Section |
|---|---------|
| 1 | [Prerequisites](#prerequisites) |
| 2 | [Installation](#installation) |
| 3 | [Quickstart](#quickstart) |
| 4 | [Commands](#commands) |
| 5 | [Environment variables](#env) |
| 6 | [Ignoring files](#ignoring) |
| 7 | [Plugging in a different LLM](#llm) |
| 8 | [AI assistant skill](#skill) |
| 9 | [Post-commit hook](#hook) |
| 10 | [SQLite schema](#schema) |
| 11 | [Dev setup](#dev) |

---

<a id="prerequisites"></a>

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| [uv](https://docs.astral.sh/uv/) | any | Used for installation and tool management |
| Python | 3.11+ | Managed automatically by `uv tool install` |
| An OpenAI-compatible LLM | — | Required only for `sourcemap enrich` |

> [!NOTE]
> `uv tool install` pulls the correct Python version automatically. You do not need to install Python separately.

> [!IMPORTANT]
> `sourcemap enrich` calls an LLM. Without a reachable endpoint (`SOURCEMAP_LLM_URL`), walk and stats work fine — only enrichment is blocked.

---

<a id="installation"></a>

## 2. Installation

```bash
uv tool install "git+https://github.com/lipex360x/sourcemap-indexer.git@main"
```

To upgrade:

```bash
uv tool upgrade sourcemap-indexer
```

To uninstall:

```bash
uv tool uninstall sourcemap-indexer
```

The binary lives at `~/.local/bin/sourcemap`. The tool environment is at `~/.local/share/uv/tools/sourcemap-indexer/`.

---

<a id="quickstart"></a>

## 3. Quickstart

```bash
cd <your-project>
sourcemap init    # create .docs/maps/, .sourcemapignore, index.db
sourcemap walk    # scan files and sync into SQLite
sourcemap enrich  # call LLM to annotate each file
sourcemap stats   # overview: total, enriched, pending
```

---

<a id="commands"></a>

## 4. Commands

### Setup

| Command | Description |
|---------|-------------|
| `sourcemap init` | Create `.docs/maps/`, `.sourcemapignore`, and `index.db` |
| `sourcemap walk` | Scan files and sync metadata into SQLite |

### Enrichment

| Command | Description |
|---------|-------------|
| `sourcemap enrich [--limit N]` | Send pending files to the LLM (validates reachability first) |
| `sourcemap enrich --force` | Re-enrich already enriched files (e.g. to fix language or layer) |
| `sourcemap enrich --file <path>` | Re-enrich a single specific file |
| `sourcemap enrich --layer unknown` | Target only files in a specific layer |
| `sourcemap enrich --language other` | Target only files in a specific language |
| `sourcemap enrich -m "<instruction>"` | Inject an extra instruction into the LLM prompt |
| `sourcemap stale` | List files whose content changed since the last enrich run |

### Exploration

| Command | Description |
|---------|-------------|
| `sourcemap stats [--page N]` | Total, enriched, and pending counts by layer and language + pending file list |
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
| `sourcemap install-skill --target <dir>` | Copy the skill file to your AI assistant's skills directory |

---

<a id="env"></a>

## 5. Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCEMAP_LLM_URL` | `http://localhost:1234/v1/chat/completions` | LLM endpoint (any OpenAI-compatible API) |
| `SOURCEMAP_LLM_MODEL` | `qwen/qwen3-coder-30b` | Model name passed to the endpoint |
| `SOURCEMAP_LLM_API_KEY` | _(empty)_ | Bearer token for authenticated providers |
| `SOURCEMAP_PAGE_SIZE` | `20` | Number of pending files shown per page in `stats` |

`sourcemap enrich` automatically reads a `.env` file from the project root before resolving env vars:

```ini
# .env  (add to .gitignore)
SOURCEMAP_LLM_URL=https://api.z.ai/api/coding/paas/v4/chat/completions
SOURCEMAP_LLM_MODEL=glm-5.1
SOURCEMAP_LLM_API_KEY=your-api-key
```

> [!NOTE]
> Variables already present in the shell environment take precedence over `.env` values.

---

<a id="ignoring"></a>

## 6. Ignoring files

`.sourcemapignore` uses the same syntax as `.gitignore`. Both files are read automatically — no extra config needed.

<details>
<summary>Built-in defaults (always excluded)</summary>

```
node_modules/   .git/         .venv/        __pycache__/
dist/           build/        .next/        .turbo/
coverage/       .docs/maps/   *.pyc         *.min.js
*.lock          *.db          *.sqlite      *.map
```

</details>

**Add project-specific patterns** to `.sourcemapignore`:

```gitignore
# exclude by extension
*.png
*.jpg
*.svg
*.ico
*.woff2

# exclude directories
secrets/
storybook-static/
public/assets/

# exclude specific files
src/generated/schema.ts
```

Pattern rules:

| Pattern | Effect |
|---------|--------|
| `*.png` | All `.png` files anywhere in the tree |
| `assets/` | Entire directory (trailing slash = directory) |
| `src/generated/` | Subdirectory under a specific path |
| `#` at line start | Comment — line is ignored |

---

<a id="llm"></a>

## 7. Plugging in a different LLM

The enrichment client targets any OpenAI-compatible endpoint:

```bash
# OpenAI
export SOURCEMAP_LLM_URL=https://api.openai.com/v1/chat/completions
export SOURCEMAP_LLM_MODEL=gpt-4o
export SOURCEMAP_LLM_API_KEY=sk-...

# Local (LM Studio)
export SOURCEMAP_LLM_URL=http://localhost:1234/v1/chat/completions
export SOURCEMAP_LLM_MODEL=your-loaded-model-name
# SOURCEMAP_LLM_API_KEY not needed for local

sourcemap enrich --limit 10
```

---

<a id="skill"></a>

## 8. AI assistant skill

Install the bundled skill file so your AI assistant can query the index directly:

```bash
# Claude Code
sourcemap install-skill --target ~/.claude/skills

# Any other tool — point to its skills directory
sourcemap install-skill --target <your-tool-skills-dir>
```

---

<a id="hook"></a>

## 9. Post-commit hook (auto-walk on every commit)

```bash
bash scripts/bash/install-hook.sh
```

Installs a `post-commit` hook that runs `sourcemap walk` after every commit, keeping the index current.

> [!NOTE]
> Enrichment is not automatic — it calls the LLM and can be slow. Run `sourcemap enrich` manually when you want updated metadata.

---

<a id="schema"></a>

## 10. SQLite schema

```sql
items        (id, path, name, language, layer, stability, purpose,
              lines, size_bytes, content_hash, llm_hash,
              needs_llm, deleted_at, created_at, updated_at, llm_at)
tags         (item_id, tag)
side_effects (item_id, effect)
invariants   (item_id, invariant)
```

Layers: `domain | infra | application | cli | hook | lib | config | doc | test | unknown`

---

<a id="dev"></a>

## 11. Dev setup

```bash
git clone https://github.com/lipex360x/sourcemap-indexer.git
cd sourcemap-indexer
uv sync
uv run pytest
```
