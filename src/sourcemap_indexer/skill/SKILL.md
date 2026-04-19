---
name: sourcemap
description: >-
  Explore and query a codebase indexed by sourcemap-indexer. Use this skill
  when the user wants to understand the project structure, find domain files,
  discover side effects, explore tags, or run free-form SQL against the index.
  Requires sourcemap init + walk to have run in the project root.
user-invocable: true
allowed-tools:
  - Bash
---

# sourcemap — codebase exploration

Query the local SQLite index built by sourcemap-indexer to understand any project without reading individual files.

## Input contract

<input_contract>

| Input | Source | Required | Validation | On invalid |
|-------|--------|----------|------------|------------|
| Project root | CWD or `--root` option | no | Directory with `.docs/maps/index.db` | Run `sourcemap init && sourcemap walk` |
| Query intent | Conversation | yes | What the user wants to know about the codebase | Ask the user to clarify |

</input_contract>

## Output contract

<output_contract>

| Artifact | Path | Persists | Format |
|----------|------|----------|--------|
| Project overview | stdout | no | Markdown summary synthesized from CLI output |
| Query results | stdout | no | Table from `sourcemap query` or preset commands |

</output_contract>

## Pre-flight

<pre_flight>

1. Check `sourcemap` is installed: `which sourcemap` — if not found, stop and tell the user to install: `uv tool install "git+https://github.com/lipex360x/sourcemap-indexer.git@main"`.
2. Check index exists: `sourcemap stats` — if it fails or shows `Total: 0`, tell the user to run `sourcemap init && sourcemap walk` first.
3. Check enrichment status from stats output — if `Pending > 0`, inform the user that results may be incomplete and suggest running `sourcemap enrich`.

</pre_flight>

## Available commands

| Command | When to use |
|---------|-------------|
| `sourcemap enrich [--limit N]` | Run LLM enrichment on pending files (validates LLM reachability first) |
| `sourcemap stats` | Overview: total files, enriched count, pending count, by layer/language |
| `sourcemap overview` | Layer × language matrix — project structure at a glance |
| `sourcemap domain` | Core business logic files (`layer=domain`, enriched only) |
| `sourcemap effects` | Files with `network` or `git` side effects — I/O boundaries |
| `sourcemap tags` | Top 30 semantic tags by frequency — project vocabulary |
| `sourcemap unstable` | Files marked `experimental` or `deprecated` — risk areas |
| `sourcemap find --layer <L>` | All files in a specific layer |
| `sourcemap find --tag <T>` | All files with a specific tag |
| `sourcemap show <path>` | Full metadata for a specific file |
| `sourcemap stale` | Files changed since last enrich run |
| `sourcemap reset` | Delete the index (offers a timestamped backup before wiping) |
| `sourcemap restore` | List available `.bak` files and restore a selected one to `index.db` |
| `sourcemap query "<sql>"` | Free-form SQL against `items`, `tags`, `side_effects`, `invariants` |

## Schema reference

```sql
items (
  id, path, name, language, layer, stability, purpose,
  lines, size_bytes, content_hash, llm_hash,
  needs_llm, deleted_at, created_at, updated_at, llm_at
)
tags        (item_id, tag)
side_effects (item_id, effect)
invariants   (item_id, invariant)
```

Layers: `domain | infra | application | cli | hook | lib | config | doc | test | unknown`
Stability: `core | stable | experimental | deprecated | unknown`
Effects: `writes_fs | spawns_process | network | git | environ`

## Steps

### 1. Run pre-flight

```bash
sourcemap stats
```

If the command fails or returns `Total: 0`, stop and instruct the user to initialize the index.

### 2. Understand what the user wants

Match the intent to one of these modes:

- **"Understand the project"** → run steps 3a
- **"Find files by concept/layer/tag"** → run steps 3b
- **"Check risk areas"** → run steps 3c
- **"Free-form query"** → run step 3d

### 3a. Full project overview

Run in sequence:

```bash
sourcemap overview
sourcemap domain
sourcemap tags
sourcemap effects
```

Synthesize a markdown summary: what the project does, its layers, key domain concepts (from tags), and I/O boundaries (from effects).

### 3b. Targeted search

```bash
sourcemap find --layer <layer>
sourcemap find --tag <tag>
sourcemap show <path>
```

Present results as a table with `path`, `layer`, `purpose`.

### 3c. Risk areas

```bash
sourcemap unstable
sourcemap stale
sourcemap effects
```

Summarize what is unstable, what has drifted since last enrich, and what touches external systems.

### 3d. Free-form SQL

```bash
sourcemap query "<user sql>"
```

Run the query and present the raw table output. If the query references unknown columns, show the schema reference above and suggest a corrected query.

## Useful query examples

```sql
-- Files that write to the filesystem
SELECT i.path, i.purpose FROM items i
JOIN side_effects s ON s.item_id = i.id
WHERE s.effect = 'writes_fs' AND i.deleted_at IS NULL;

-- Most complex files (by line count)
SELECT path, language, layer, lines FROM items
WHERE deleted_at IS NULL ORDER BY lines DESC LIMIT 20;

-- Files not yet enriched
SELECT path, language FROM items
WHERE needs_llm = 1 AND deleted_at IS NULL ORDER BY path;

-- Cross-reference: tag + layer
SELECT i.path, i.layer, t.tag FROM items i
JOIN tags t ON t.item_id = i.id
WHERE t.tag = 'authentication' ORDER BY i.layer;
```

## Self-audit

<self_audit>

1. **Pre-flight passed?** — `sourcemap stats` ran without error and returned files
2. **Enrichment complete enough?** — warned user if `Pending > 0` and enrichment may affect results
3. **SQL is valid?** — any free-form query used correct column names from the schema reference
4. **Summary is grounded?** — all claims in the project overview come from actual CLI output

</self_audit>

## Error handling

| Failure | Strategy |
|---------|----------|
| `sourcemap` not found | Tell user to install: `uv tool install "git+https://github.com/lipex360x/sourcemap-indexer.git@main"` |
| Index not found or empty | Tell user to run `sourcemap init && sourcemap walk` |
| `(no results)` on preset commands | Inform user that enrichment hasn't run yet for that data; suggest `sourcemap enrich --limit N` |
| SQL error in `query` | Show the schema reference and suggest the corrected query |
| LLM unreachable on `enrich` | Check `SOURCEMAP_LLM_URL` env var and confirm the server is running |
| User asks to reset the index | Run `sourcemap reset` — warns about irreversibility, offers backup (default Y) |
| User wants to undo a reset | Run `sourcemap restore` — lists timestamped `.bak` files for selection |
