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
| Project root | CWD or `--root` option | no | Directory with `.sourcemap/index.db` | Run `sourcemap init && sourcemap walk` |
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

> **For project discovery, run `sourcemap brief` — single call, complete context.**

| Command | When to use |
|---------|-------------|
| `sourcemap brief` | **Project discovery** — project metadata (when `project.yaml` exists), totals, architecture, domain files, I/O boundaries, vocabulary, risk areas in one shot |
| `sourcemap brief --verbose` (or `-v`) | Same as `brief` plus a **Files by layer** section listing every enriched file with its 1-line `purpose`, grouped by layer. Use when aggregate counts are not enough to locate a concept — especially on documentation-heavy projects where most files live in support layers |
| `sourcemap chapters [--layer L]` | Table of contents — enriched files grouped by layer and sorted by path. Ideal for documentation-heavy projects |
| `sourcemap contracts [--layer L]` | Invariants grouped by layer and file — the semantic contracts captured during enrichment. Use this instead of `brief` to read every invariant |
| `sourcemap enrich [--limit N]` | Run LLM enrichment on pending files. Provider selected via `SOURCEMAP_LLM_PROVIDER` (`http` default, or `claude-cli` for Claude subscription) |
| `sourcemap enrich --force` | Re-enrich already enriched files (e.g. to fix language or layer) |
| `sourcemap enrich --layer <L>` | Target only files in a specific layer (useful for `unknown`) |
| `sourcemap enrich --language <L>` | Target only files in a specific language |
| `sourcemap enrich -m "<instruction>"` | Inject an extra instruction into the LLM prompt |
| `sourcemap doctor` | **Setup check** — verify LLM provider config and connectivity. Outputs `OK:` / `FAIL:` lines for provider, binary/URL, model, ping, and llm-log status. Exit 1 on any failure. Run before `enrich` to diagnose configuration problems |
| `sourcemap validate` | **CI gate** — verify every file on disk is indexed. Outputs `PASS:sourcemap-db` (exit 0) or one `MISSING:path` per unindexed file (exit 1). Run after `walk` in pre-commit hooks |
| `sourcemap stats [--page N]` | Overview with pending file list (paginated, 20/page by default) |
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

Layers: `domain | infra | application | cli | hook | lib | config | doc | test | unknown` — plus any user-defined names declared in `.sourcemap/layers.yaml`
Stability: `core | stable | experimental | deprecated | unknown`
Effects: `writes_fs | spawns_process | network | git | environ`

### Project metadata

`brief` also reads `.sourcemap/project.yaml` (optional) to show a header with `name`, `version`, `purpose`, `audience`, and `license`. Any missing field is skipped. The file is never sent to the LLM — purely display.

### Documentation-heavy projects

For projects that are primarily documentation (blueprints, standards, specifications), declare doc-oriented layers in `.sourcemap/layers.yaml` so `brief`, `chapters`, and `find --layer` work at the right granularity. Example:

```yaml
layers:
  - foundations
  - enforcement
  - operations
  - shared
  - stacks
  - meta
```

After adding custom layers, run `sourcemap enrich --force` so every file is reclassified.

When custom layers are declared, the system prompt automatically tells the LLM to prefer a user-defined layer over a generic default (`doc`, `config`, `unknown`) whenever the top-level directory matches. If a mismatch slips through, `sourcemap enrich` prints a **Layer mismatches** section at the end of its run, listing the offending files and their expected layer — no log inspection required.

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
- **"Read the chapters / table of contents"** → `sourcemap chapters [--layer L]`
- **"Read every contract / invariant / schema constraint"** → `sourcemap contracts [--layer L]`

### 3a. Full project overview

```bash
sourcemap brief
```

Output sections: totals, Architecture (layer × language matrix), Domain (top enriched domain files with purpose), I/O Boundaries (side effects by count), Vocabulary (top 15 tags), Risk Areas (experimental/deprecated files).

If the default sections do not surface the concept the user is looking for — typical when most files live in support layers (e.g. `stacks`, `foundations`, `enforcement` on documentation-heavy projects) — re-run with `--verbose` to expand a **Files by layer** section that lists every enriched file with its `purpose`, grouped by layer.

Synthesize a markdown summary from this single output: what the project does, its layers, key domain concepts, and I/O boundaries.

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
| LLM unreachable on `enrich` | Run `sourcemap doctor` first — it diagnoses provider, binary, connectivity, and log status in one shot |
| User asks to reset the index | Run `sourcemap reset` — warns about irreversibility, offers backup (default Y) |
| User wants to undo a reset | Run `sourcemap restore` — lists timestamped `.bak` files for selection |
