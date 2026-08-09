#!/usr/bin/env bash
#
# Homework 4 — 4-agent bug-fix pipeline, single-command runner.
#
# Runs every agent in `agents/` in the required order, automatically loading each agent's
# declared skills into its system prompt. Each stage is a headless Claude Code session
# (`claude -p`) using the model declared in that agent's frontmatter.
#
#   ./run-pipeline.sh                 # run the whole pipeline (skips stages already done)
#   ./run-pipeline.sh --force         # re-run every stage from scratch
#   ./run-pipeline.sh --dry-run       # show the plan: stages, models, skills, cache decisions
#   ./run-pipeline.sh --from bug-fixer
#   ./run-pipeline.sh --only security-verifier --force
#   ./run-pipeline.sh --bug BUG-002
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---------------------------------------------------------------------------- configuration

# Required run order: research → verification → planning → fix → security → tests.
STAGES=(
  bug-researcher
  research-verifier
  bug-planner
  bug-fixer
  security-verifier
  unit-test-generator
)

BUG_ID="BUG-001"
TEST_CMD="python3 -m pytest"
MAX_USD_PER_STAGE="${PIPELINE_MAX_USD:-5}"

FORCE=0
DRY_RUN=0
FROM=""
ONLY=""

# ---------------------------------------------------------------------------- presentation

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; RESET=""
fi

say()  { printf '%s\n' "$*"; }
info() { printf '%s\n' "${DIM}$*${RESET}"; }
ok()   { printf '%s\n' "${GREEN}$*${RESET}"; }
warn() { printf '%s\n' "${YELLOW}$*${RESET}"; }
die()  { printf '%s\n' "${RED}✗ $*${RESET}" >&2; exit 1; }

rule() { printf '%s\n' "${DIM}────────────────────────────────────────────────────────────────────────────${RESET}"; }

usage() {
  sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

# ---------------------------------------------------------------------------- arguments

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)   FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --from)    FROM="${2:-}"; shift 2 ;;
    --only)    ONLY="${2:-}"; shift 2 ;;
    --bug)     BUG_ID="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

stage_known() {
  local candidate="$1"
  for stage in "${STAGES[@]}"; do [[ "$stage" == "$candidate" ]] && return 0; done
  return 1
}

[[ -n "$FROM" ]] && ! stage_known "$FROM" && die "--from: unknown stage '$FROM'"
[[ -n "$ONLY" ]] && ! stage_known "$ONLY" && die "--only: unknown stage '$ONLY'"

BUG_DIR="context/bugs/$BUG_ID"

# ---------------------------------------------------------------------------- frontmatter

# Print the YAML frontmatter block of an agent file.
frontmatter() {
  awk 'NR==1 && $0=="---" { inside=1; next } inside && $0=="---" { exit } inside { print }' "$1"
}

# Print the value of a top-level frontmatter key (empty when absent or blank).
fm_get() {
  frontmatter "$1" | awk -v key="$2" '
    index($0, key ":") == 1 { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }
  '
}

# Print the agent body (everything after the frontmatter block).
agent_body() {
  awk 'NR==1 && $0=="---" { inside=1; next } inside && $0=="---" { inside=0; body=1; next } body || !inside { print }' "$1"
}

# Split a comma-separated frontmatter value into trimmed lines.
split_list() {
  printf '%s' "$1" | tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' || true
}

metric() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null || printf 'n/a'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    print("n/a"); raise SystemExit
value = data.get(sys.argv[2])
if value is None:
    print("n/a")
elif sys.argv[2] == "total_cost_usd":
    print(f"${float(value):.4f}")
elif sys.argv[2] == "duration_ms":
    print(f"{float(value) / 1000:.0f}s")
else:
    print(value)
PY
}

# ---------------------------------------------------------------------------- preflight

preflight() {
  command -v claude  >/dev/null 2>&1 || die "the 'claude' CLI is not on PATH (see HOWTORUN.md)"
  command -v python3 >/dev/null 2>&1 || die "python3 is not on PATH"
  python3 -c "import pytest" >/dev/null 2>&1 || die "pytest is missing: pip install -r requirements.txt"
  [[ -f "$BUG_DIR/bug-context.md" ]] || die "missing bug context: $BUG_DIR/bug-context.md"

  local stage agent_file skill
  for stage in "${STAGES[@]}"; do
    agent_file="agents/$stage.agent.md"
    [[ -f "$agent_file" ]] || die "missing agent definition: $agent_file"
    [[ -n "$(fm_get "$agent_file" model)" ]]  || die "$agent_file: frontmatter has no 'model'"
    [[ -n "$(fm_get "$agent_file" output)" ]] || die "$agent_file: frontmatter has no 'output'"
    while read -r skill; do
      [[ -f "$skill" ]] || die "$agent_file declares a missing skill: $skill"
    done < <(split_list "$(fm_get "$agent_file" skills)")
  done
}

# ---------------------------------------------------------------------------- stage runner

RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="artifacts/logs/$RUN_ID"

declare -a SUMMARY_ROWS=()

# Build the system prompt for a stage: agent body + the full text of every declared skill.
build_system_prompt() {
  local agent_file="$1" skill
  agent_body "$agent_file" | sed "s/{{BUG_ID}}/$BUG_ID/g"
  while read -r skill; do
    printf '\n\n%s\n\n' "---"
    printf '# LOADED SKILL — %s\n\n' "$skill"
    printf 'This skill is mandatory for you. Apply it literally.\n\n'
    cat "$skill"
  done < <(split_list "$(fm_get "$agent_file" skills)")
}

build_task_prompt() {
  local name="$1" output="$2" inputs="$3"
  cat <<PROMPT
You are running as the "$name" agent, one stage of an automated bug-fix pipeline. This is a
non-interactive run: nobody can answer questions, so make the best decision available and document it.

Bug ID: $BUG_ID
Bug folder: $BUG_DIR
Working directory: $(pwd)
Project test command: $TEST_CMD

Input files (read them before doing anything else):
$inputs

Required output file (you must create it): $output

Rules for this run:
- Follow your agent definition and any loaded skill exactly; they are in your system prompt.
- Write every artifact in English, as Markdown, and print your own progress messages in English too.
- Stay inside the working directory. Never touch git (no commits, no branches, no stashing).
- Do not ask for confirmation and do not stop early; finish your role.
- End your reply with the path of the output file you wrote.
PROMPT
}

run_stage() {
  local index="$1" name="$2"
  local agent_file="agents/$name.agent.md"
  local model output tools inputs skills_list
  local padded_index status detail duration cost turns

  padded_index="$(printf '%02d' "$index")"
  model="$(fm_get "$agent_file" model)"
  output="$(fm_get "$agent_file" output | sed "s/{{BUG_ID}}/$BUG_ID/g")"
  tools="$(fm_get "$agent_file" allowed_tools | tr ',' ' ')"
  inputs="$(split_list "$(fm_get "$agent_file" inputs)" | sed "s/{{BUG_ID}}/$BUG_ID/g" | sed 's/^/  - /')"
  skills_list="$(split_list "$(fm_get "$agent_file" skills)" | paste -sd ', ' - )"
  [[ -z "$skills_list" ]] && skills_list="(none)"
  [[ -z "$inputs" ]] && inputs="  (none declared)"
  [[ -z "$tools" ]] && tools="Read Grep Glob Bash Write Edit"

  rule
  say "${BOLD}${BLUE}▶ Stage $padded_index/${#STAGES[@]} — $name${RESET}"
  say "  ${DIM}model  :${RESET} $model"
  say "  ${DIM}skills :${RESET} $skills_list"
  say "  ${DIM}output :${RESET} $output"

  if [[ $DRY_RUN -eq 1 ]]; then
    info "  ⋯ dry run — would invoke: claude -p --model $model --allowed-tools \"$tools\""
    if [[ -f "$output" && $FORCE -eq 0 ]]; then
      info "    (output exists — this stage would be skipped as cached; add --force to re-run)"
      SUMMARY_ROWS+=("$padded_index|$name|$model|DRY-RUN/CACHED|-|-|-|$output")
    else
      SUMMARY_ROWS+=("$padded_index|$name|$model|DRY-RUN|-|-|-|$output")
    fi
    return 0
  fi

  if [[ -f "$output" && $FORCE -eq 0 ]]; then
    warn "  ⤼ cached — output already exists, stage skipped (use --force to re-run)"
    SUMMARY_ROWS+=("$padded_index|$name|$model|CACHED|-|-|-|$output")
    return 0
  fi

  mkdir -p "$LOG_DIR" "$(dirname "$output")"

  local log_file="$LOG_DIR/$padded_index-$name.log"
  local json_file="$LOG_DIR/$padded_index-$name.result.json"
  local system_prompt task_prompt started
  system_prompt="$(build_system_prompt "$agent_file")"
  task_prompt="$(build_task_prompt "$name" "$output" "$inputs")"

  say "  ${DIM}running…${RESET}"
  started=$SECONDS
  set +e
  # shellcheck disable=SC2086 # $tools is an intentional word-split list of tool names
  claude -p "$task_prompt" \
    --model "$model" \
    --append-system-prompt "$system_prompt" \
    --allowed-tools $tools \
    --permission-mode acceptEdits \
    --output-format stream-json --verbose \
    --no-session-persistence \
    --safe-mode \
    --max-budget-usd "$MAX_USD_PER_STAGE" \
    2> >(tee -a "$log_file.stderr" >&2) \
    | python3 pipeline/stream_render.py "$json_file" | tee -a "$log_file"
  local pipe_status=("${PIPESTATUS[@]}")
  set -e
  duration="$((SECONDS - started))s"

  if [[ "${pipe_status[0]}" -ne 0 ]]; then
    die "stage '$name' failed: claude exited ${pipe_status[0]} (log: $log_file.stderr)"
  fi
  if [[ "${pipe_status[1]}" -ne 0 ]]; then
    die "stage '$name' reported an agent-level error (log: $log_file)"
  fi
  [[ -f "$output" ]] || die "stage '$name' did not produce its declared output: $output"

  cost="$(metric "$json_file" total_cost_usd)"
  turns="$(metric "$json_file" num_turns)"
  detail="$(wc -l <"$output" | tr -d ' ') lines"
  ok "  ✓ wrote $output ($detail) — ${duration}, ${cost}, ${turns} turns"
  SUMMARY_ROWS+=("$padded_index|$name|$model|OK|$duration|$cost|$turns|$output")
}

# ---------------------------------------------------------------------------- gates

security_gate() {
  local report="$BUG_DIR/security-report.md"
  [[ -f "$report" ]] || return 0
  local critical high
  critical="$(grep -c 'Severity\*\*:[[:space:]]*CRITICAL' "$report" || true)"
  high="$(grep -c 'Severity\*\*:[[:space:]]*HIGH' "$report" || true)"
  if [[ "$critical" -gt 0 || "$high" -gt 0 ]]; then
    rule
    warn "⚠ SECURITY GATE — $critical CRITICAL and $high HIGH finding(s) in $report"
    warn "  The security verifier writes reports only and never edits code."
    warn "  Review the report, extend $BUG_DIR/implementation-plan.md, then:"
    warn "    ./run-pipeline.sh --only bug-fixer --force && ./run-pipeline.sh --force"
  else
    ok "✓ security gate — no CRITICAL or HIGH findings in $report"
  fi
}

write_run_summary() {
  local summary="artifacts/pipeline-run.md"
  mkdir -p artifacts
  {
    printf '# Pipeline Run — %s\n\n' "$RUN_ID"
    printf '| Bug | Run ID | Stages | Logs |\n|---|---|---|---|\n'
    printf '| `%s` | `%s` | %s | `%s/` |\n\n' "$BUG_ID" "$RUN_ID" "${#SUMMARY_ROWS[@]}" "$LOG_DIR"
    printf '| # | Agent | Model | Status | Duration | Cost | Turns | Output |\n'
    printf '|---|---|---|---|---|---|---|---|\n'
    local row
    for row in "${SUMMARY_ROWS[@]}"; do
      IFS='|' read -r idx name model status duration cost turns output <<<"$row"
      printf '| %s | `%s` | `%s` | %s | %s | %s | %s | `%s` |\n' \
        "$idx" "$name" "$model" "$status" "$duration" "$cost" "$turns" "$output"
    done
    printf '\n## Final test run\n\n```\n%s\n```\n' "$FINAL_TEST_OUTPUT"
  } >"$summary"
  info "run summary written to $summary"
}

print_summary_table() {
  rule
  say "${BOLD}Pipeline summary${RESET} ${DIM}(run $RUN_ID)${RESET}"
  printf '%s\n' "${DIM}  #  agent                  model              status    time   cost${RESET}"
  local row
  for row in "${SUMMARY_ROWS[@]}"; do
    IFS='|' read -r idx name model status duration cost turns output <<<"$row"
    local colour="$GREEN"
    [[ "$status" == "CACHED"  ]] && colour="$YELLOW"
    [[ "$status" == DRY-RUN*  ]] && colour="$CYAN"
    printf '  %-2s %-22s %-18s %s%-14s%s %-6s %s\n' \
      "$idx" "$name" "$model" "$colour" "$status" "$RESET" "$duration" "$cost"
  done
}

# ---------------------------------------------------------------------------- main

say ""
say "${BOLD}Homework 4 — 4-agent bug-fix pipeline${RESET}"
say "${DIM}bug $BUG_ID · ${#STAGES[@]} stages · run $RUN_ID${RESET}"

preflight
ok "✓ preflight: claude CLI, python3, pytest, agent definitions and skills present"

skipping=0
[[ -n "$FROM" ]] && skipping=1

index=0
for stage in "${STAGES[@]}"; do
  index=$((index + 1))
  if [[ -n "$ONLY" && "$stage" != "$ONLY" ]]; then continue; fi
  if [[ $skipping -eq 1 ]]; then
    if [[ "$stage" == "$FROM" ]]; then skipping=0; else
      info "  ↷ stage $(printf '%02d' "$index") — $stage (skipped by --from $FROM)"
      continue
    fi
  fi
  run_stage "$index" "$stage"
  [[ "$stage" == "security-verifier" ]] && security_gate
done

rule
say "${BOLD}Running the project test suite${RESET} ${DIM}($TEST_CMD)${RESET}"
set +e
FINAL_TEST_OUTPUT="$($TEST_CMD 2>&1 | tail -15)"
TEST_STATUS=$?
set -e
printf '%s\n' "$FINAL_TEST_OUTPUT"

print_summary_table
[[ $DRY_RUN -eq 1 ]] || write_run_summary

rule
if [[ $TEST_STATUS -eq 0 ]]; then
  ok "✓ pipeline finished — artifacts in $BUG_DIR/, logs in $LOG_DIR/"
else
  die "pipeline finished but the test suite is red — see the output above"
fi
