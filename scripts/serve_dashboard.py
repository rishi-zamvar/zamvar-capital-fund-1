"""scripts/serve_dashboard.py (Phase 9) — run the iOS dashboard shim on loopback or Tailscale ONLY.

    DASHBOARD_TOKEN=<secret>  serve_dashboard.py --host "$(tailscale ip -4)"   # phone over Tailscale
    DASHBOARD_TOKEN=<secret>  serve_dashboard.py                               # 127.0.0.1 (default)

The bind guard refuses 0.0.0.0 / LAN / public addresses / hostnames: only loopback or the Tailscale
CGNAT range 100.64.0.0/10 is accepted, so the trading host is never exposed beyond the tailnet. The
shared-secret token (>= 16 chars) comes from the environment, never argv. Run the MD chat inside a
Claude Code-authenticated host (the seam is the same claude-agent-sdk the desk uses).

PAPER ONLY: the shim's only writes are approve/reject through paper_ledger's gate.
"""

from __future__ import annotations

import argparse
import ipaddress
import os

from catalyst_trader import dashboard_api
from catalyst_trader import db as _db

TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def check_bind_host(host: str) -> str:
    """Return `host` if it is a loopback or Tailscale (100.64.0.0/10) IP literal; else raise."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(f"bind host must be an IP literal (loopback or Tailscale), got {host!r}") from None
    if ip.is_loopback or (ip.version == 4 and ip in TAILSCALE_CGNAT):
        return host
    raise ValueError(f"refusing to bind {host}: only loopback or Tailscale 100.64.0.0/10 is allowed")


def load_token() -> str:
    token = os.environ.get("DASHBOARD_TOKEN", "")
    if len(token) < dashboard_api.MIN_TOKEN_LEN:
        raise ValueError(f"set DASHBOARD_TOKEN (>= {dashboard_api.MIN_TOKEN_LEN} chars), "
                         "e.g. `python -c 'import secrets; print(secrets.token_urlsafe(32))'`")
    return token


def main():
    ap = argparse.ArgumentParser(description="Fund 1 iOS dashboard shim (loopback/Tailscale only).")
    ap.add_argument("--host", default="127.0.0.1", help="loopback or Tailscale IP (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--db", default="catalyst.db", help="catalyst.db path (default: catalyst.db)")
    args = ap.parse_args()

    host = check_bind_host(args.host)
    token = load_token()
    conn = _db.connect(args.db)
    _db.migrate(conn)  # same as paper_run: the review column (017) must exist before serving
    conn.close()

    import uvicorn

    uvicorn.run(dashboard_api.create_app(args.db, token), host=host, port=args.port)


if __name__ == "__main__":
    main()
