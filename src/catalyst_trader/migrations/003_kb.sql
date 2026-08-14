-- Phase 2 KB. Graph-shaped generic node/edge tables + vec0 KNN table.
-- 384-dim aligns with the intended real embedder (MiniLM); dimension is baked into vec0 DDL and cannot be ALTERed.

CREATE TABLE kb_node (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN
    ('company','drug','indication','trial','catalyst','outcome',
     'trade','playbook','evidence_source','prediction','hedge_peer')),
  ref_id INTEGER,                    -- optional link to Phase-1 rows (e.g. catalyst.id) — don't copy data in
  attrs_json TEXT,                   -- kind-specific payload
  confidence REAL,                   -- KB-05: playbooks/predictions surface confidence here
  created_at TEXT NOT NULL
);

CREATE TABLE kb_edge (
  id INTEGER PRIMARY KEY,
  src_id INTEGER NOT NULL REFERENCES kb_node(id),
  rel TEXT NOT NULL CHECK (rel IN
    ('DEVELOPS','TARGETS','TESTED_IN','ABOUT','RESULTED_IN','PLACED_ON',
     'USED_PLAYBOOK','REALIZED','MADE_BY','CITES','ANALOG_OF','HEDGE_PEER')),
  dst_id INTEGER NOT NULL REFERENCES kb_node(id),
  weight REAL,                       -- ANALOG_OF similarity, HEDGE_PEER strength
  attrs_json TEXT,                   -- HEDGE_PEER: {mechanism, payoff_direction:+1/-1}
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE kb_vec USING vec0(node_id integer primary key, embedding float[384] distance_metric=cosine);

CREATE INDEX idx_edge_src ON kb_edge(src_id, rel);
CREATE INDEX idx_edge_dst ON kb_edge(dst_id, rel);
CREATE INDEX idx_node_kind ON kb_node(kind);
