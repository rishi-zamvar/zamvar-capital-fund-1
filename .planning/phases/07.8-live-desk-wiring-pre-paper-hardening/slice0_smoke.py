"""Slice 0 smoke test — does the desk's live LLM seam work under Max/inside-Claude-Code, no API key?
Stage 1: basic json_schema structured output + auth. One real sonnet call."""
import asyncio, os, time
from pydantic import BaseModel
from catalyst_trader.desk.runtime import run_structured


class Answer(BaseModel):
    sum: int
    one_word_mood: str


async def main():
    print("ANTHROPIC_API_KEY set:", bool(os.environ.get("ANTHROPIC_API_KEY")))
    t0 = time.monotonic()
    out = await run_structured(
        "Add 21 and 21. Return the integer sum and a one-word mood.",
        Answer,
        model="sonnet",
    )
    dt = time.monotonic() - t0
    print(f"OK  latency={dt:.1f}s  -> sum={out.sum} mood={out.one_word_mood!r}")
    assert out.sum == 42, out.sum
    print("STAGE-1 PASS: live structured output validated with no API key.")


asyncio.run(main())
