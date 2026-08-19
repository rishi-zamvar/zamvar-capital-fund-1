"""Slice 0 stage 2 — does the model invoke the in-process quant MCP tool and get the real value back?
Force an rnpv tool call (precise math the model can't fake), assert it matches the deterministic tool."""
import asyncio, time
from pydantic import BaseModel
from catalyst_trader import db
from catalyst_trader.desk.runtime import run_structured
from catalyst_trader.desk.tools import build_quant_server
from catalyst_trader import quant

CASH = [[2, 120.0, 0.6], [3, 300.0, 0.6], [4, 450.0, 0.6]]  # (year, cashflow, cumulative_pos)
RATE = 0.12
COSTS = [[0, 40.0, 1.0], [1, 60.0, 0.9]]                    # (year, cost, prob_reach)


class RnpvOut(BaseModel):
    rnpv_value: float
    tool_called: bool


async def main():
    conn = db.connect(":memory:"); db.migrate(conn)
    srv = {"quant": build_quant_server(conn)}
    truth = quant.rnpv(cashflows=CASH, discount_rate=RATE, costs=COSTS).value
    prompt = (
        "You MUST call the mcp__quant__rnpv tool (do not compute it yourself) with "
        f"cashflows={CASH}, discount_rate={RATE}, costs={COSTS}. "
        "Return its numeric result as rnpv_value and tool_called=true."
    )
    t0 = time.monotonic()
    out = await run_structured(prompt, RnpvOut, mcp_servers=srv,
                               allowed_tools=["mcp__quant__rnpv"], model="sonnet")
    dt = time.monotonic() - t0
    print(f"latency={dt:.1f}s  model rnpv_value={out.rnpv_value}  deterministic={truth}")
    assert abs(out.rnpv_value - truth) < 0.01, f"MISMATCH: {out.rnpv_value} vs {truth} — tool NOT really called"
    print("STAGE-2 PASS: model invoked the in-process quant MCP tool; value matches the deterministic tool exactly.")


asyncio.run(main())
