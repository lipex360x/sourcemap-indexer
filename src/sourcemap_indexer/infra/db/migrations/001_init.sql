PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS _migrations (
  name        TEXT PRIMARY KEY,
  applied_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
  id             TEXT PRIMARY KEY,
  path           TEXT NOT NULL UNIQUE,
  name           TEXT NOT NULL,
  language       TEXT NOT NULL,
  lines          INTEGER NOT NULL DEFAULT 0,
  size_bytes     INTEGER NOT NULL DEFAULT 0,
  content_hash   TEXT NOT NULL,
  last_modified  INTEGER NOT NULL DEFAULT 0,

  entry_point    INTEGER NOT NULL DEFAULT 0,
  has_test       INTEGER,
  test_path      TEXT,

  purpose        TEXT,
  layer          TEXT NOT NULL DEFAULT 'unknown',
  stability      TEXT NOT NULL DEFAULT 'unknown',

  needs_llm      INTEGER NOT NULL DEFAULT 1,
  llm_hash       TEXT,
  llm_at         INTEGER,

  deleted_at     INTEGER,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
  item_id  TEXT NOT NULL,
  tag      TEXT NOT NULL,
  PRIMARY KEY (item_id, tag),
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS side_effects (
  item_id  TEXT NOT NULL,
  effect   TEXT NOT NULL,
  PRIMARY KEY (item_id, effect),
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invariants (
  item_id    TEXT NOT NULL,
  position   INTEGER NOT NULL,
  invariant  TEXT NOT NULL,
  PRIMARY KEY (item_id, position),
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_items_language  ON items(language);
CREATE INDEX IF NOT EXISTS idx_items_layer     ON items(layer);
CREATE INDEX IF NOT EXISTS idx_items_needs_llm ON items(needs_llm) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_items_deleted   ON items(deleted_at);
CREATE INDEX IF NOT EXISTS idx_tags_tag        ON tags(tag);
