#!/usr/bin/env bash
# Live build-status view for the autonomous run. Reads the real repo/.planning — always current.
# Usage:  bash scripts/build-status.sh          # print once
#         bash scripts/build-status.sh watch     # refresh every 5s (Ctrl-C to stop)
set -euo pipefail
cd "$(dirname "$0")/.."
GSD="$HOME/.claude/get-shit-done/bin/gsd-tools.cjs"

render() {
  local now last age mins
  now=$(date +%s)
  last=$(git log -1 --format=%ct 2>/dev/null || echo "$now")
  age=$(( now - last )); mins=$(( age / 60 ))
  echo "════════════════════════════════════════════════════════════"
  echo " ZAMVAR CAPITAL — FUND 1 · autonomous build   $(date '+%H:%M:%S')"
  echo "════════════════════════════════════════════════════════════"
  # phase table
  node "$GSD" roadmap analyze 2>/dev/null > /tmp/zc_roadmap.json || echo '{}' > /tmp/zc_roadmap.json
  python3 - /tmp/zc_roadmap.json <<'PY' 2>/dev/null || echo " (roadmap analyze unavailable)"
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    d={}
ph=d.get("phases",[])
done=sum(1 for p in ph if p.get("disk_status")=="complete")
print(f" phases complete: {done}/{len(ph)}")
for p in ph:
    st=p.get("disk_status","?")
    mark={"complete":"OK","in_progress":">>"}.get(st,"..")
    print(f"   [{mark}] {p.get('number'):>2}. {p.get('name')}  ({st})")
PY
  # current phase stage (by artifacts present in highest phase dir)
  local dir; dir=$(ls -d .planning/phases/*/ 2>/dev/null | sort | tail -1 || true)
  if [ -n "${dir:-}" ]; then
    echo " current phase dir: ${dir}"
    printf "   stage:"
    for a in CONTEXT RESEARCH VALIDATION PLAN SUMMARY VERIFICATION; do
      if ls "${dir}"*-"$a".md >/dev/null 2>&1; then printf " %s✓" "$a"; else printf " %s·" "$a"; fi
    done; echo
  fi
  echo " commits: $(git rev-list --count HEAD)   |   last commit ${mins}m ${age}s ago"
  echo "   └─ $(git log -1 --format='%h %s')"
  if [ "$age" -gt 900 ]; then
    echo "   ⚠ no commit in >15m — a step may be running long or stalled. Check the CC session."
  else
    echo "   ● active (commits recently)"
  fi
  echo "════════════════════════════════════════════════════════════"
}

if [ "${1:-}" = "watch" ]; then
  while true; do clear; render; sleep 5; done
else
  render
fi
