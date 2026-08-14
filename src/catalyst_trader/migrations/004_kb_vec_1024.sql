-- Widen the KB vector store 384 -> 1024 for a real open-source semantic embedder
-- (BAAI/bge-large-en-v1.5, 1024-dim, via fastembed/ONNX — local, private, no API).
-- vec0 dimension is baked into the DDL and cannot be ALTERed, so drop + recreate.
-- Safe: kb_vec holds no persisted production data yet (populated at runtime from kb_node).
DROP TABLE IF EXISTS kb_vec;
CREATE VIRTUAL TABLE kb_vec USING vec0(node_id integer primary key, embedding float[1024] distance_metric=cosine);
