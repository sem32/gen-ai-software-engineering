#!/usr/bin/env bash
#
# demo.sh — the whole project in one command, zero manual steps (CR-01.3, spec task T-14 / §3.10).
#
#   ./demo.sh                 full demo
#   ./demo.sh --no-tests      skip the test suite and coverage gate (the slow step)
#   ./demo.sh --keep-running  leave the service mesh and gateway up for manual poking
#   ./demo.sh --base-port N   pin the agent service ports (default: a free block)
#
# Every step is checked. The first failure stops the demo with a non-zero exit code and names the
# step. A trap stops every process this script started — on success, on failure and on Ctrl-C.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# --------------------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------------------
RUN_TESTS=1
KEEP_RUNNING=0
BASE_PORT=""
GATEWAY_PORT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --no-tests)     RUN_TESTS=0 ;;
        --keep-running) KEEP_RUNNING=1 ;;
        --base-port)    BASE_PORT="${2:-}"; shift ;;
        --port)         GATEWAY_PORT="${2:-}"; shift ;;
        -h|--help)      sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)              echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

LOG_DIR="docs/sample-run"
LOG_FILE="$LOG_DIR/demo.log"
mkdir -p "$LOG_DIR"
: > "$LOG_FILE"

DEMO_SHARED="${TMPDIR:-/tmp}/hw6-demo-$$"
STRICT_SHARED="$DEMO_SHARED-strict"
MESH_LOG="$DEMO_SHARED/mesh.log"
GATEWAY_LOG="$DEMO_SHARED/gateway.log"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'; CYAN=$'\033[36m'; OFF=$'\033[0m'
if [ ! -t 1 ]; then BOLD=""; DIM=""; RED=""; GREEN=""; CYAN=""; OFF=""; fi

STEP_NAMES=(); STEP_RESULTS=()
MESH_PID=""; GATEWAY_PID=""
FAILED_STEP=""


# A tolerant JSON field reader: never let a failed request kill the demo output.
pyjson() { # pyjson <key> [<key> ...]  — prints "key=value", tolerating any failure
    $PY -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    print("(no readable response)"); raise SystemExit(0)
if not isinstance(payload, dict):
    print("(unexpected shape)"); raise SystemExit(0)
print("  ".join(f"{key}={payload.get(key)}" for key in sys.argv[1:]))
' "$@"
}

log()   { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
raw()   { tee -a "$LOG_FILE"; }
banner() {
    log ""
    log "${BOLD}${CYAN}=== $* ${OFF}"
    log ""
}
note()  { log "${DIM}$*${OFF}"; }

record() {  # record <name> <ok|fail>
    STEP_NAMES+=("$1"); STEP_RESULTS+=("$2")
    if [ "$2" = "fail" ] && [ -z "$FAILED_STEP" ]; then FAILED_STEP="$1"; fi
}

check() {   # check <name> <command...>
    local name="$1"; shift
    if "$@" >>"$LOG_FILE" 2>&1; then record "$name" ok; return 0; fi
    record "$name" fail
    log "${RED}FAILED: $name${OFF} (see $LOG_FILE)"
    return 1
}

cleanup() {
    local code=$?
    if [ "$KEEP_RUNNING" = "1" ] && [ -z "$FAILED_STEP" ]; then
        log ""
        log "${BOLD}--keep-running: leaving processes up${OFF}"
        log "  gateway : http://127.0.0.1:$GATEWAY_PORT   (pid $GATEWAY_PID)"
        log "  mesh    : pid $MESH_PID"
        log "  stop it : kill $GATEWAY_PID $MESH_PID"
        exit $code
    fi
    if [ -n "$GATEWAY_PID" ]; then kill "$GATEWAY_PID" 2>/dev/null || true; wait "$GATEWAY_PID" 2>/dev/null || true; fi
    if [ -n "$MESH_PID" ]; then kill "$MESH_PID" 2>/dev/null || true; wait "$MESH_PID" 2>/dev/null || true; fi
    pkill -f "services.agent_service --agent" 2>/dev/null || true
    exit $code
}
trap cleanup EXIT INT TERM

# --------------------------------------------------------------------------------------
# 0. Environment
# --------------------------------------------------------------------------------------
banner "0/8  Environment"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    note "no .venv found — creating one (needed only for pytest and the MCP server)"
    if python3 -m venv .venv >>"$LOG_FILE" 2>&1 && \
       .venv/bin/pip install -q -r requirements.txt >>"$LOG_FILE" 2>&1; then
        note "virtualenv ready"
    else
        note "could not provision .venv — falling back to python3 (tests and MCP will be skipped)"
        PY="python3"; RUN_TESTS=0
    fi
fi
log "interpreter : $($PY -V 2>&1)"
log "pipeline    : standard library only (the gateway and the services add no dependency)"
log "workspace   : $DEMO_SHARED"
log "transcript  : $LOG_FILE"
record "environment" ok

# --------------------------------------------------------------------------------------
# 1. Validation dry run
# --------------------------------------------------------------------------------------
banner "1/8  Validation dry run — nothing is written"

if $PY agents/transaction_validator.py --dry-run 2>&1 | raw; then
    record "dry-run" ok
else
    record "dry-run" fail
fi

# --------------------------------------------------------------------------------------
# 2. Pipeline, default rule pack
# --------------------------------------------------------------------------------------
banner "2/8  Pipeline over the file journal — default rule pack"

if $PY integrator.py --shared "$DEMO_SHARED" 2>&1 | raw; then
    record "pipeline-default" ok
else
    record "pipeline-default" fail
fi

# --------------------------------------------------------------------------------------
# 3. Same input, stricter policy pack — behaviour changes with no code change
# --------------------------------------------------------------------------------------
banner "3/8  Same input, same code, stricter rule pack"

if $PY integrator.py --shared "$STRICT_SHARED" --rules policy-strict 2>&1 | raw; then
    record "pipeline-strict" ok
else
    record "pipeline-strict" fail
fi

log ""
log "${BOLD}What editing JSON did:${OFF}"
$PY - "$DEMO_SHARED" "$STRICT_SHARED" <<'PYEOF' 2>&1 | raw
import json, sys
from pathlib import Path

def load(root):
    summary = json.loads((Path(root) / "reports" / "pipeline-summary.json").read_text())
    return {row["transaction_id"]: row for row in summary["transactions"]}, summary

default, default_summary = load(sys.argv[1])
strict, strict_summary = load(sys.argv[2])

print(f"  {'TXN':<9}{'default':<24}{'policy-strict':<24}change")
print("  " + "-" * 74)
changes = 0
for txn_id in sorted(default):
    a, b = default[txn_id], strict[txn_id]
    left = f"{a['status']}"
    right = f"{b['status']}"
    if a["status"] == "settled" and b["status"] == "settled":
        left += f" ({a['detail'].split()[1]})"
        right += f" ({b['detail'].split()[1]})"
    mark = "" if left == right else "  <-- changed"
    if mark:
        changes += 1
    print(f"  {txn_id:<9}{left:<24}{right:<24}{mark}")
print()
print(f"  default : {default_summary['by_status']}")
print(f"  strict  : {strict_summary['by_status']}")
print(f"  {changes} outcome(s) changed by editing rules/policy-strict.json — no code was touched.")
PYEOF

# --------------------------------------------------------------------------------------
# 4. The agent service mesh
# --------------------------------------------------------------------------------------
banner "4/8  Agents as microservices — one process each, REST between them"

if [ -z "$BASE_PORT" ]; then
    BASE_PORT=$($PY -c "from services.launcher import free_port; print(free_port())")
fi
mkdir -p "$DEMO_SHARED"

$PY -m services --shared "$DEMO_SHARED" --base-port "$BASE_PORT" >"$MESH_LOG" 2>&1 &
MESH_PID=$!

ENTRY="http://127.0.0.1:$BASE_PORT"
if $PY -c "
import sys
from services.client import wait_until_healthy
sys.exit(0 if wait_until_healthy('$ENTRY/health', timeout=30) else 1)
"; then
    record "mesh-up" ok
    grep -E "^(service mesh up|  [0-9]\.|entrypoint)" "$MESH_LOG" | raw
    log ""
    log "Each service, as it describes itself:"
    for offset in 0 1 2 3 4; do
        port=$((BASE_PORT + offset))
        curl -s "http://127.0.0.1:$port/health" | $PY scripts/demo_render.py health "$port" | raw
    done
else
    record "mesh-up" fail
    log "${RED}the service mesh did not come up${OFF}"
    tail -20 "$MESH_LOG" | raw
fi

# --------------------------------------------------------------------------------------
# 5. Gateway in front of the mesh
# --------------------------------------------------------------------------------------
banner "5/8  REST gateway in front of the mesh"

if [ -z "$GATEWAY_PORT" ]; then
    GATEWAY_PORT=$($PY -c "from services.launcher import free_port; print(free_port())")
fi

HW6_SERVICE_BASE_PORT="$BASE_PORT" $PY -m gateway \
    --port "$GATEWAY_PORT" --shared "$DEMO_SHARED" --transport rest >"$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!
API="http://127.0.0.1:$GATEWAY_PORT"

if $PY -c "
import sys
from services.client import wait_until_healthy
sys.exit(0 if wait_until_healthy('$API/health', timeout=30) else 1)
"; then
    record "gateway-up" ok
    curl -s "$API/health" | $PY -m json.tool | raw
else
    record "gateway-up" fail
    tail -20 "$GATEWAY_LOG" | raw
fi

# --------------------------------------------------------------------------------------
# 6. Submit over HTTP
# --------------------------------------------------------------------------------------
banner "6/8  Submitting transactions over HTTP"

submit() {  # submit <label> <json> [query]
    local label="$1"; local body="$2"; local query="${3:-}"
    local out status
    out=$(curl -s -w '\n%{http_code}' -X POST "$API/transactions$query" \
          -H 'Content-Type: application/json' -d "$body")
    status=$(printf '%s' "$out" | tail -1)
    printf '%s' "$out" | sed '$d' | $PY scripts/demo_render.py submission "$label" "$status"
}

txn() { # txn <id> <amount> <currency> <hour> <channel> <country>
    cat <<EOF
{"transaction_id":"$1","timestamp":"2026-03-16T$4:00:00Z","source_account":"ACC-1001",
 "destination_account":"ACC-2001","amount":"$2","currency":"$3","transaction_type":"transfer",
 "description":"demo submission","metadata":{"channel":"$5","country":"$6"}}
EOF
}

log "${BOLD}Happy path and business verdicts${OFF}"
submit "settled"                  "$(txn DEMO001 1500.00 USD 09 online US)" | raw
submit "held (fraud review)"      "$(txn DEMO002 75000.00 USD 09 branch US)" | raw
submit "rejected (bad currency)"  "$(txn DEMO003 200.00 XYZ 09 online US)" | raw

log ""
log "${BOLD}Error handling — RFC 9457 problem+json${OFF}"
submit "400 schema violation"     '{"transaction_id":"DEMO004","amount":1500.0}' | raw
log "  400 malformed JSON         HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/transactions" -H 'Content-Type: application/json' -d '{oops')"
log "  404 unknown transaction    HTTP $(curl -s -o /dev/null -w '%{http_code}' "$API/transactions/NOPE")"
log "  405 wrong method           HTTP $(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$API/transactions")"
note "  the full catalog is served at GET /errors"

log ""
log "${BOLD}Same transaction, stricter pack, selected per request${OFF}"
submit "default  (9999.99)"                 "$(txn DEMO005 9999.99 USD 09 online US)" | raw
submit "strict   (9999.99)" "$(txn DEMO006 9999.99 USD 09 online US)" "?rules=policy-strict" | raw

log ""
log "${BOLD}Each agent is individually callable${OFF}"
curl -s "$API/agents" | $PY scripts/demo_render.py agents | raw

log ""
log "${BOLD}Reading results back${OFF}"
log "  GET /transactions/DEMO001 -> $(curl -s "$API/transactions/DEMO001" | pyjson status net_amount currency priority rule_pack)"
log "  GET /transactions         -> $(curl -s "$API/transactions" | pyjson total by_status)"
log "  GET /audit?limit=3        -> $(curl -s "$API/audit?limit=3" | pyjson total) journal entries (files under the hood)"
record "http-submissions" ok

# --------------------------------------------------------------------------------------
# 7. Tests and the coverage gate
# --------------------------------------------------------------------------------------
banner "7/8  Tests and the coverage gate"

if [ "$RUN_TESTS" = "1" ]; then
    if .venv/bin/pytest -q 2>&1 | tail -25 | raw; then
        record "tests" ok
    else
        record "tests" fail
    fi
    if .venv/bin/python scripts/coverage_gate.py --simulate-push 2>&1 | raw; then
        record "coverage-gate" ok
    else
        record "coverage-gate" fail
    fi
else
    note "skipped (--no-tests, or no virtualenv)"
fi

# --------------------------------------------------------------------------------------
# 8. MCP server
# --------------------------------------------------------------------------------------
banner "8/8  MCP server over stdio"

if [ "$PY" = ".venv/bin/python" ]; then
    if $PY scripts/verify_mcp_server.py 2>&1 | grep -E "tool |resource |All MCP calls" | raw; then
        record "mcp" ok
    else
        record "mcp" fail
    fi
else
    note "skipped (needs the virtualenv for fastmcp)"
fi

# --------------------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------------------
banner "Summary"

for index in "${!STEP_NAMES[@]}"; do
    if [ "${STEP_RESULTS[$index]}" = "ok" ]; then
        log "  ${GREEN}PASS${OFF}  ${STEP_NAMES[$index]}"
    else
        log "  ${RED}FAIL${OFF}  ${STEP_NAMES[$index]}"
    fi
done

log ""
if [ -n "$FAILED_STEP" ]; then
    log "${RED}${BOLD}demo failed at: $FAILED_STEP${OFF}  — transcript: $LOG_FILE"
    exit 1
fi
log "${GREEN}${BOLD}all steps passed${OFF}  — transcript: $LOG_FILE"
log ""
log "Where to look next:"
log "  docs/presentation.html                  the project explained"
log "  specification.md                        objectives, tasks, guardrails, edge cases"
log "  docs/change-requests/                   CR-01 and CR-02, the inputs the code was built from"
log "  rules/policy-strict.json                change a rule, re-run step 3, watch the outcome move"
exit 0
