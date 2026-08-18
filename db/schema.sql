PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS topics (
  id TEXT PRIMARY KEY,
  track TEXT NOT NULL,
  title_hint TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT 'A1A2',
  category TEXT NOT NULL DEFAULT 'dialogue',
  status TEXT NOT NULL DEFAULT 'pending',
  order_index INTEGER NOT NULL DEFAULT 0,
  last_used_at TEXT,
  use_count INTEGER NOT NULL DEFAULT 0,
  youtube_title TEXT   -- canonical numbered YouTube title, e.g. "🇳🇱 Dutch Grammar #1: ..."
);

CREATE TABLE IF NOT EXISTS canonical_scripts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id TEXT NOT NULL,
  language TEXT NOT NULL,
  title TEXT NOT NULL,
  script_json TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS language_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_script_id INTEGER NOT NULL,
  language TEXT NOT NULL,
  title TEXT NOT NULL,
  script_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(canonical_script_id) REFERENCES canonical_scripts(id)
);

CREATE TABLE IF NOT EXISTS publish_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_script_id INTEGER NOT NULL,
  playlist_track TEXT NOT NULL,
  playlist_name TEXT,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL,
  youtube_video_id TEXT,
  artifact_path TEXT,
  video_file_path TEXT,
  artifact_json TEXT,
  artifact_file_path TEXT,
  status_history TEXT,
  published_at TEXT,
  status_detail TEXT,
  updated_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(canonical_script_id) REFERENCES canonical_scripts(id)
);

CREATE TABLE IF NOT EXISTS content_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_script_id INTEGER NOT NULL,
  metric_key TEXT NOT NULL,
  metric_value REAL NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(canonical_script_id) REFERENCES canonical_scripts(id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_topic ON canonical_scripts(topic_id);
CREATE INDEX IF NOT EXISTS idx_publish_scheduled ON publish_jobs(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_publish_status ON publish_jobs(status);