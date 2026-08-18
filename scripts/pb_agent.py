"""Claude-Code-agent extraction harness (no API key — runs on the Max subscription via spawned
agents). The agent IS the complete_fn:
  --prompt <cid>            -> prints build_prompt(build_bundle(cid)); the agent answers with JSON
  --insert <cid> <json>     -> extract_record(bundle, ->that JSON) + insert_catalyst_record (KB write)
Reuses the shipped pipeline verbatim (validation, cite-drop, fact-overwrite, embedding). Uses the
project's db.connect so the sqlite-vec (vec0) extension + row_factory load correctly.
"""
import argparse, sys
from catalyst_trader import db as _db
from catalyst_trader import kb
from catalyst_trader.playbook.extract import build_bundle, build_prompt, extract_record
from catalyst_trader.playbook.store import insert_catalyst_record

DB = "catalyst.db"


def _conn():
    c = _db.connect(DB)
    return c


def cmd_prompt(cid):
    c = _conn()
    b = build_bundle(c, cid)
    if b is None:
        print("SKIP_NO_BUNDLE"); return
    print(build_prompt(b))


def cmd_insert(cid, json_path):
    c = _conn()
    b = build_bundle(c, cid)
    if b is None:
        print("SKIP_NO_BUNDLE"); return
    txt = open(json_path, encoding="utf-8").read()
    rec = extract_record(b, lambda _prompt: txt)
    if rec is None:
        print("DROP_EXTRACT_REJECTED"); return
    embed = kb.default_embedder()
    nid = insert_catalyst_record(c, rec, embed)
    c.commit()
    print(f"INSERTED cid={cid} node={nid} label={rec.outcome_label} move={rec.signed_move}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", type=int)
    ap.add_argument("--insert", type=int)
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.prompt is not None:
        cmd_prompt(a.prompt)
    elif a.insert is not None:
        if not a.json:
            sys.exit("--insert requires --json <path>")
        cmd_insert(a.insert, a.json)
    else:
        sys.exit("use --prompt <cid> or --insert <cid> --json <path>")
