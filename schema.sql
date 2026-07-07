-- D1 schema — paste into the D1 console in the Cloudflare dashboard
-- (Storage & Databases -> D1 -> your database -> Console) and run once.
CREATE TABLE IF NOT EXISTS edits (
  slug        TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  died        TEXT,            -- date of death from Wikidata, YYYY-MM-DD
  description TEXT DEFAULT '',
  wiki_url    TEXT DEFAULT '',
  detected_at TEXT,            -- ISO timestamp when the watcher found them
  pageviews   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_edits_died ON edits (died DESC);
