# Security Report — BUG-001

## Scope

Review scope is the **Changed Files** table of `context/bugs/BUG-001/fix-summary.md`:

| File | Functions reviewed |
|---|---|
| `src/auth.py` | module header (`DEFAULT_ADMIN_TOKEN` removed, `import hmac` added), `expected_token`, `verify_admin_token`, `require_admin` |
| `src/storage.py` | module import (line 9), `list_tasks`, `export_report` |
| `src/stats.py` | `average_completion_days` |

Each changed file was read in full, not only the diff hunks, and every changed function was followed
to its entry point in `src/cli.py` (`export` → `src/cli.py:97`; `admin clear` → `src/cli.py:102`;
`stats` → `src/cli.py:93`; `list` → `src/cli.py:78`). `src/models.py` and `src/cli.py` were read for
caller/callee context but are **not in scope** — issues found there are filed under *Out of Scope
Observations*. Test files were read only to confirm the fix is exercised
(`tests/test_cli.py:59`, `tests/test_storage.py:63`); they are excluded from the findings.

**Threat model**: a single-binary local CLI run with the invoking user's own privileges, persisting to
a user-owned JSON file, with one shared admin token in an environment variable guarding one
destructive command (`admin clear`). The privilege boundaries that actually exist are (a) *other local
users on the same host* and (b) *untrusted filenames/store contents fed to the CLI by a wrapper
script*. There is no network surface, no HTTP, no database and no HTML rendering.

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 4 |
| INFO | 1 |

**Highest severity found: MEDIUM.**

**Verdict**: all four security concerns the fix claimed to close are genuinely closed — the hardcoded
admin token is gone, the comparison is constant-time, the rejection message no longer echoes the
supplied token, and the export containment check resists relative traversal, absolute paths, symlinked
files *and* symlinked directories. The fix introduced no high-impact defect. What remains is one
pre-existing MEDIUM (the admin token is passed on the command line, so it is readable from the process
table by any local user) plus four LOW items, one of which (an authentication-state oracle in the new
error message) was introduced by this fix.

## Verified Remediations

| Concern from the fix | Closed? | Evidence |
|---|---|---|
| S3a — hardcoded fallback `DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"` allowed `admin clear` on any unconfigured install | **Yes** | `src/auth.py:8` — the constant is gone; `src/auth.py:22-25` raises `AuthError` when `TASKTRACKER_ADMIN_TOKEN` is unset **or empty**. Confirmed: `env -u TASKTRACKER_ADMIN_TOKEN … admin clear --token "hw4-admin-secret"` → `forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured`, `exit=3`; `TASKTRACKER_ADMIN_TOKEN="" … --token ""` → same, `exit=3` (an empty env var does not become an empty accepted token). Grep across the repo shows no remaining `DEFAULT_ADMIN_TOKEN` reference in `src/`. |
| S3b — token comparison was not constant-time | **Yes** | `src/auth.py:37` uses `hmac.compare_digest` on UTF-8 bytes. Residual note, not a finding: `compare_digest` is content-constant-time but its runtime tracks the shorter operand, so token *length* is theoretically observable. Unreachable here — per-attempt noise is dominated by process spawn and the token is not remotely probed. |
| S3b — rejection error echoed the caller's token (`f"admin token rejected: {provided!r}"`) | **Yes** | `src/auth.py:43` is a plain literal with no interpolation. Confirmed empirically, not only by inspection: with `TASKTRACKER_ADMIN_TOKEN="real-secret-value"` and `--token "guess-abc"`, `grep -c "real-secret-value\|guess-abc"` over combined stdout+stderr returned `0`. Neither the expected nor the supplied token appears in output. |
| S3.2 / F4 — `export` allowed path traversal and absolute-path escape out of the export directory | **Yes**, and more broadly than claimed | `src/storage.py:100-105`. The check compares **resolved** paths (`base.resolve()` against `target.resolve().parents`), not strings, so it also defeats symlink escapes the fix summary never claimed. All rejected with `exit=2` and nothing written: `../outside/pwn1.txt`, an absolute `/tmp/secver/outside/pwn2.txt`, a pre-existing symlinked *file* inside the export dir pointing outside, a pre-existing symlinked *directory* inside the export dir, `""` and `"."`. A legitimate nested name (`a/b/c/ok.txt`) still succeeds. `find` over the export dir and `ls` over the outside dir confirmed no file escaped. |
| S1 — `stats` crashed with `ZeroDivisionError` when nothing was completed (availability / unhandled-crash class) | **Yes** | `src/stats.py:51-53` returns `0.0` before the division. No traceback path remains through `summarize` for the empty-completed case. |
| S2 — `list --sort priority` sorted alphabetically | **Yes** (no security relevance) | `src/storage.py:69-73`. The new `PRIORITY_RANK[task.priority]` lookup cannot raise `KeyError` from stored data because `Task.__post_init__` (`src/models.py:35-38`) rejects any priority outside `PRIORITIES` before a `Task` can exist, and `list_tasks` only ever receives `Task` objects. Verified as a non-issue rather than assumed. |

## Findings

### SEC-1 — Admin token is passed as a command-line argument and is readable from the process table

- **Severity**: MEDIUM
- **Location**: `src/cli.py:61` (`admin.add_argument("--token", …)`), consumed at `src/cli.py:102` → `src/auth.py:40`
- **Category**: hardcoded/exposed secrets — credential disclosure
- **Description**: `--token` is the only way to supply the admin credential. Command-line arguments
  are world-readable on this platform (`ps -o args`) and on Linux via `/proc/<pid>/cmdline`, so the
  application's sole secret is exposed to every other local user for the lifetime of the process. The
  fix's own documentation now actively instructs this usage (`src/cli.py:10`,
  `HOWTORUN.md:78`, `HOWTORUN.md:178`). This is not a defect the fix created, but the fix materially
  raised its value: before, the credential was a published constant nobody needed to steal; now it is
  a real operator-chosen secret, and `--token` is the one place it is exposed in clear text.
- **Attack scenario**: an unprivileged local user runs `while :; do ps -o args= -A | grep -- --token; done`
  (or a single `ps` if they can predict the maintenance window). The operator runs
  `python -m src.cli admin clear --token "$TASKTRACKER_ADMIN_TOKEN"`. The attacker reads the expanded
  token from the process table. Note the mitigating factor that keeps this out of HIGH: holding the
  token alone does not let the attacker clear the operator's store, because `TaskStore.save`
  (`src/storage.py:36`) still needs filesystem write permission on a store file written `0644`
  (verified). The harm is disclosure of the credential itself — which matters because it is a single
  shared, non-rotating, non-expiring secret likely reused across installs.
- **Proof**: run under `/tmp`, backgrounding a process carrying a fake token, then reading it back:
  ```
  $ ps -o pid=,args= -p 41328
  41328 …/Python -c … --token S3CRET-ADMIN-VALUE
  ```
  The value is fully visible to any local user.
- **Remediation**: make the environment variable (or an interactive prompt) the primary input path and
  demote `--token`. In `build_parser` (`src/cli.py:59-61`), either drop `--token` entirely and have
  `require_admin` read `TASKTRACKER_ADMIN_TOKEN` from the caller's own environment, or keep the flag
  only as an explicit opt-in and default to a prompt:
  ```python
  admin.add_argument("--token-stdin", action="store_true",
                     help="read the admin token from stdin instead of argv")
  # in main(): token = sys.stdin.readline().rstrip("\n") if args.token_stdin else getpass.getpass("admin token: ")
  ```
  Update `src/cli.py:10` and `HOWTORUN.md:78` so the documented path no longer puts the secret in argv.
- **Introduced by this fix**: no (pre-existing — `src/cli.py` was not touched)

### SEC-2 — No minimum token strength and no throttling on `verify_admin_token`

- **Severity**: LOW
- **Location**: `src/auth.py:22-25` (`expected_token`) and `src/auth.py:28-37` (`verify_admin_token`)
- **Category**: missing / weak input validation
- **Description**: `expected_token` accepts any non-empty string as a valid installation token — a
  single character, or a single space, both pass. `verify_admin_token` has no attempt counter, no
  backoff, no lockout and no audit record, so guesses are limited only by CPU. The fix correctly
  removed the *known* default token but did not replace it with any policy on what an acceptable
  replacement token looks like, so an operator can silently downgrade to a one-character secret.
- **Attack scenario**: an operator sets `TASKTRACKER_ADMIN_TOKEN=x` (accepted with no warning). Any
  party able to import `src.auth` or invoke the CLI enumerates the short keyspace in well under a
  second and recovers the token, then uses it wherever that secret is honoured. Severity is held at
  LOW because in the default single-user deployment the guesser already has direct write access to the
  JSON store and does not need `admin clear` to destroy it — the token guards no privilege the local
  attacker lacks. The finding matters chiefly as an amplifier of SEC-1.
- **Proof**: run under `/tmp` against a deliberately weak token:
  ```
  $ TASKTRACKER_ADMIN_TOKEN="abcd" python3 - <<'PY'
  … brute force a..zzzz via verify_admin_token …
  PY
  recovered token='abcd' after 19010 attempts in 0.02s -> no rate limit, no lockout, no audit trail
  ```
  Separately confirmed via the CLI that `TASKTRACKER_ADMIN_TOKEN="x"` and
  `TASKTRACKER_ADMIN_TOKEN=" "` are both accepted as configured (`cleared 0 task(s)`, `exit=0`).
- **Remediation**: enforce a floor in `expected_token` before returning, and strip surrounding
  whitespace so a blank-looking value cannot pass:
  ```python
  configured = os.environ.get(ENV_VAR, "").strip()
  if not configured:
      raise AuthError(f"admin commands are disabled: {ENV_VAR} is not configured")
  if len(configured) < 32:
      raise AuthError(f"admin commands are disabled: {ENV_VAR} must be at least 32 characters")
  ```
  Additionally, log each rejected attempt from `require_admin` (`src/auth.py:40-43`) to stderr or a
  file so brute forcing is at least observable.
- **Introduced by this fix**: no (pre-existing gap; the fix changed this function but did not create
  the weakness — though it is the natural place the policy now belongs)

### SEC-3 — Error messages distinguish "admin not configured" from "wrong token"

- **Severity**: LOW
- **Location**: `src/auth.py:24` versus `src/auth.py:43`, surfaced at `src/cli.py:110-112`
- **Category**: information disclosure
- **Description**: the two failure paths emit different strings on stderr, both with exit code 3.
  `forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured` versus
  `forbidden: admin token rejected`. This is exactly the "wrong user vs wrong token" oracle pattern:
  it tells an unauthenticated caller whether the admin facility is armed at all, and therefore whether
  guessing is worth attempting. The message also names the exact environment variable holding the
  secret, which is useful reconnaissance for anyone who later gains a partial process/environment read.
- **Attack scenario**: an attacker with the ability to invoke the CLI runs
  `admin clear --token anything`. A response of `admin token rejected` tells them a live token exists
  on this host and is worth brute forcing (SEC-2) or stealing from the process table (SEC-1); a
  response of `admin commands are disabled` tells them to stop wasting effort and look elsewhere. No
  token material leaks — hence LOW, at the bottom of the scale, not INFO only because it is a
  deliberate authentication-state disclosure rather than an incidental one.
- **Proof**: run under `/tmp`, four invocations of the real CLI:
  ```
  # unset env var
  forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured   exit=3
  # empty env var
  forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured   exit=3
  # configured, wrong token
  forbidden: admin token rejected                                                     exit=3
  # configured, no --token at all
  forbidden: admin token rejected                                                     exit=3
  ```
  The two states are trivially distinguishable from stderr alone.
- **Remediation**: return one message to the caller and keep the diagnostic detail on an operator-only
  channel. In `require_admin` (`src/auth.py:40-43`), catch the configuration error and collapse both
  paths:
  ```python
  def require_admin(provided: str | None) -> None:
      try:
          ok = verify_admin_token(provided)
      except AuthError:
          ok = False          # log the configuration detail to a log file, not to the caller
      if not ok:
          raise AuthError("admin token rejected")
  ```
  Operators keep discoverability through `HOWTORUN.md:44-48`, which already documents the requirement.
- **Introduced by this fix**: **yes** — the "admin commands are disabled: …" message is new in
  Change 3

### SEC-4 — Store loading leaks full stack traces on malformed or non-JSON input

- **Severity**: LOW
- **Location**: `src/storage.py:27` (`json.loads`) and `src/storage.py:30` (`Task.from_dict`), reached from `src/cli.py:78`, `:93`, `:97`
- **Category**: information disclosure / missing input validation (error path)
- **Description**: `TaskStore.load` guards only the "not a list" case (`src/storage.py:28-29`).
  `json.JSONDecodeError` and `UnicodeDecodeError` from `read_text`/`json.loads`, and `TypeError` from
  `int(raw["id"])` in `Task.from_dict` (`src/models.py:70`), are **not** subclasses of
  `ValidationError` and are not among the exceptions `main` catches (`src/cli.py:107-112`). They
  escape as uncaught tracebacks that print absolute interpreter paths, the exact Python version, and
  interpreter source lines. The failure is loud, not silent, so it does **not** fail open — but it
  discloses environment detail and turns any malformed store into an unhandled crash. `--store` is
  attacker-influenceable whenever the CLI is wrapped by a script.
- **Attack scenario**: a wrapper script passes a user-supplied path or a user-writable file as
  `--store`. The user places non-JSON, binary, or structurally valid but wrongly typed JSON there. The
  next `list`/`stats`/`export` dumps a traceback into whatever log or terminal collects the wrapper's
  stderr, revealing `/Library/Frameworks/Python.framework/Versions/3.14/...` and the install layout,
  and returning an unhandled exit status instead of the documented `2`.
- **Proof**: run under `/tmp` against three crafted store files:
  ```
  # non-JSON text
  File "/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/json/decoder.py", line 363, in raw_decode
  json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  # binary file
  File "<frozen codecs>", line 325, in decode
  UnicodeDecodeError: 'utf-8' codec can't decode byte 0xca in position 0: invalid continuation byte
  # '[{"id": {"a":1}, "title": "x"}]'
      id=int(raw["id"]),
  TypeError: int() argument must be a string, a bytes-like object or a real number, not 'dict'
  ```
- **Remediation**: convert parse failures into the domain error the CLI already handles, inside
  `TaskStore.load` (`src/storage.py:23-30`):
  ```python
  try:
      raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
  except (json.JSONDecodeError, UnicodeDecodeError) as exc:
      raise ValidationError(f"store file is not valid JSON: {self.path}") from exc
  ```
  and guard the coercions in `Task.from_dict` (`src/models.py:69-77`) so a wrong field type raises
  `ValidationError` rather than `TypeError`. Do not include file *contents* in the message.
- **Introduced by this fix**: no (pre-existing — `load` and `from_dict` were not changed; reported
  because `src/storage.py` is in scope)

### SEC-5 — Export containment check is non-atomic (TOCTOU between check and write)

- **Severity**: LOW
- **Location**: `src/storage.py:102` (check) versus `src/storage.py:106-107` (`mkdir` + `write_text`)
- **Category**: path traversal (race condition)
- **Description**: the containment decision is made against `target.resolve()`, then the write is
  performed against the *unresolved* `target` path in two separate later syscalls. Nothing pins the
  inode between them. If any path component under `export_dir` is replaced by a symlink after
  `resolve()` returns and before `write_text` opens the file, the write follows the new symlink and
  lands outside the validated base. `write_text` opens with `"w"`, which follows symlinks and
  truncates.
- **Attack scenario**: the export directory is shared or group-writable (e.g. a build agent's
  `exports/`). The victim runs `export sub/report.txt`. An attacker loops, replacing `exports/sub`
  with a symlink to a sensitive directory. On a winning interleaving the report is written — and any
  existing file truncated — at `<attacker target>/report.txt`, outside the base the check approved.
  Severity is LOW because it needs write access to the export directory (which already permits
  clobbering files there directly) and a won race.
- **Proof**: reasoned — no safe proof available. Demonstrating it requires a nondeterministic
  symlink-swap race against a live write, which risks truncating an unintended file; that is a
  destructive experiment and was not run. The non-atomicity is unambiguous from
  `src/storage.py:102` and `:107` being separate operations on a mutable filesystem.
- **Remediation**: write through the validated path and refuse to follow links. In `export_report`,
  resolve once and reuse the resolved value, then open with `O_NOFOLLOW` / exclusive semantics:
  ```python
  resolved = target.resolve()
  if base.resolve() not in resolved.parents:
      raise ValidationError(...)
  resolved.parent.mkdir(parents=True, exist_ok=True)
  fd = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
  with os.fdopen(fd, "w", encoding="utf-8") as handle:
      handle.write(render_report(tasks))
  ```
  Note this also fixes a smaller inconsistency: the function currently validates `target.resolve()`
  but returns and writes the unresolved `target`.
- **Introduced by this fix**: **yes, partially** — the check itself is new in Change 5, and it was
  written as a non-atomic check-then-write. The underlying write call is unchanged.

### SEC-6 — `--export-dir` and `--store` are unconstrained, so the containment base is caller-chosen

- **Severity**: INFO
- **Location**: `src/cli.py:57` (`--export-dir`), `src/cli.py:35-39` (`--store`), consumed at `src/storage.py:100` and `src/storage.py:34-36`
- **Category**: missing input validation (documented as by-design)
- **Description**: `export_report` constrains `filename` relative to `export_dir`, but `export_dir`
  is itself arbitrary caller input with no allowlist, so the containment check binds the *leaf* name
  only. The same holds for `--store`, which will create parent directories and write anywhere the
  user can write. `export_report` also overwrites an existing file inside the base silently, and
  `TaskStore.save` writes the store with the default `0644` umask result — world-readable.
- **Attack scenario**: `python -m src.cli export pwn6.txt --export-dir /tmp/outside/deep/dir`
  writes outside any notion of an export root. This is **not** a privilege escalation: the CLI runs
  with the invoking user's own rights and that user could write the same file with a shell redirect.
  It is recorded at INFO so the limit of the S3.2/F4 remediation is explicit — the fix protects a
  wrapper that fixes `--export-dir` and forwards an untrusted `filename`, and nothing more.
- **Proof**: run under `/tmp`:
  ```
  $ python3 -m src.cli --store /tmp/secver/s.json export "pwn6.txt" --export-dir /tmp/secver/outside/deep/dir
  report written to /tmp/secver/outside/deep/dir/pwn6.txt
  exit=0
  $ python3 -m src.cli --store /tmp/secver/outside/arbitrary/store.json add "written anywhere"
  added #1: written anywhere (priority=medium)
  $ ls -l /tmp/secver/outside/arbitrary/store.json
  -rw-r--r--  1 sem  wheel  179 … store.json
  ```
- **Remediation**: no code change required for the CLI's own threat model. If the CLI is ever exposed
  behind a wrapper that forwards untrusted arguments, that wrapper must pin `--export-dir` and
  `--store` rather than relying on `export_report`. If defence in depth is wanted, restrict
  `export_dir` in `export_report` to a configured root and tighten the store's mode with
  `os.chmod(self.path, 0o600)` after `save`.
- **Introduced by this fix**: no (pre-existing; `src/cli.py` was not touched)

## Checklist Coverage

| Scan class | Result |
|---|---|
| Injection — command | **Clean.** No `subprocess`, `os.system`, `os.popen` or shell invocation anywhere in the changed files or their call path. |
| Injection — path | See **SEC-5**, **SEC-6**. Core containment logic in `export_report` is sound (SEC-1..4 of the *Verified Remediations* table). |
| Injection — SQL | **Not applicable.** No database; persistence is a single JSON file (`src/storage.py:27`, `:36`). |
| Injection — template | **Not applicable.** `render_report` (`src/storage.py:79-87`) builds a plain-text string with f-strings; no template engine is involved and the output is never interpreted. |
| Injection — `eval`/`exec` | **Clean.** Neither appears in `src/`; verified by grep. |
| Injection — unsafe deserialization | **Clean.** `json.loads` only (`src/storage.py:27`); no `pickle`, `yaml.load`, `marshal` or `shelve`. Unknown fields are rejected (`src/models.py:63-66`); malformed types crash loudly rather than executing — see **SEC-4**. |
| Path traversal — string vs resolved comparison | **Clean / verified fixed.** `src/storage.py:102` compares `base.resolve()` against `target.resolve().parents` — resolved paths, not strings. |
| Path traversal — symlink escape | **Clean / verified fixed.** Symlinked file and symlinked directory inside the export dir both rejected (empirically tested). Residual race: **SEC-5**. |
| Path traversal — absolute-path input | **Clean / verified fixed.** Absolute `filename` rejected with `exit=2`, nothing written. |
| Path traversal — check before normalization | **Clean.** `resolve()` is applied to both operands before the comparison, and the comparison precedes `mkdir` and `write_text` (`src/storage.py:102` before `:106-107`). |
| Hardcoded secrets — default credentials | **Clean / verified fixed.** `DEFAULT_ADMIN_TOKEN` removed; no credential literal remains in `src/`. Grep across the repo finds `hw4-admin-secret` only in documentation and pipeline artefacts describing the fix, never in code. |
| Hardcoded secrets — tokens/keys in source | **Clean.** The only test credential is `s3cret-for-test`, set via `monkeypatch.setenv` in `tests/test_cli.py:59` — test-scoped, not shipped. |
| Hardcoded secrets — secrets in errors/logs | **Clean / verified fixed** for the rejection path (`src/auth.py:43`, empirically confirmed no echo). Related exposure through argv: **SEC-1**. |
| Insecure comparison — non-constant-time | **Clean / verified fixed.** `hmac.compare_digest` at `src/auth.py:37`. |
| Insecure comparison — truncated / case-folded | **Clean.** Full-length byte comparison; no `lower()`, `startswith`, slicing or normalization is applied to the token on either side. |
| Missing / weak input validation — unbounded input | **SEC-4** (no size or type guard on the store file). Titles and tags are also unbounded, but bound only the user's own file — noted, not filed. |
| Missing / weak input validation — unchecked types | **SEC-4** (`int(raw["id"])`, `list(raw.get("tags", []))` in `src/models.py:69-77`). |
| Missing / weak input validation — missing authorization on destructive action | **Clean.** `admin clear` is the only destructive command and is gated by `require_admin` before `store.clear()` (`src/cli.py:102-103`). The gate fails **closed**: when no token is configured, `expected_token` raises out of `verify_admin_token` and `require_admin` without being swallowed, and `main` maps `AuthError` to exit 3 (`src/cli.py:110-112`). Verified there is no other caller of `verify_admin_token` that could treat the raise as a falsy-but-continue. |
| Missing / weak input validation — token strength | **SEC-2**. |
| Missing / weak input validation — error paths failing open | **Clean.** Every error path examined (`src/auth.py:24`, `:36`, `:43`; `src/storage.py:103`; `src/cli.py:107-112`) terminates the command with a non-zero exit before the destructive or write operation. **SEC-4**'s uncaught exceptions abort rather than continue. |
| Information disclosure — stack traces | **SEC-4**. |
| Information disclosure — secret echo | **Clean / verified fixed** (grep count `0` over combined output for both the expected and supplied token). |
| Information disclosure — verbose errors distinguishing failure states | **SEC-3**. |
| Unsafe dependencies | **Clean, with one note.** The fix added no dependency; `requirements.txt` contains only `pytest>=8.0`, unchanged. That constraint is **unpinned** (`>=`, no upper bound, no hash), which is a supply-chain weakness in principle, but it is a pre-existing test-only dependency not introduced or modified here — recorded as a note, not a finding. `hmac` and `os` (`src/auth.py:5-6`) are standard library. |
| XSS | **Not applicable.** The changed code renders no markup and handles no HTTP. `render_report` emits plain text to a file. |
| CSRF | **Not applicable.** No HTTP surface, no sessions, no cookies. |

## Out of Scope Observations

These are outside the Changed Files table and are recorded for completeness only.

1. **`src/cli.py:107`** — `main` catches `KeyError` and prints it as `error: {exc}`. `KeyError`'s
   `str()` is the repr of the missing key, so `store.complete` raising
   `KeyError(f"no task with id {task_id}")` (`src/storage.py:56`) is displayed to the user with
   surrounding quotes: `error: 'no task with id 7'`. Cosmetic, not a security issue.
2. **`src/cli.py:114`** — `main` returns `1` when no command branch matched. Unreachable today
   (`required=True` at `src/cli.py:40`), but it is a silent fallthrough that would report failure
   without any message if a future sub-command were added without a branch.
3. **`src/models.py:63`** — `known = {f for f in (...)}` is a set comprehension over a literal tuple;
   a set literal is equivalent and clearer. Style only, listed here because it sits in the
   deserialization path reviewed for **SEC-4**.
4. **`src/models.py:44`, `:46` and `src/storage.py:53`** — `date.today()` is called at model and store
   level, so completion timestamps are unauthenticated local wall-clock values. Irrelevant for this
   application, but any future audit-trail requirement cannot rely on them.

## References

**Files read (in full):**

- `context/bugs/BUG-001/fix-summary.md` (lines 1-286) — scope, claimed remediations, Changed Files table
- `src/auth.py` (lines 1-44) — `expected_token` `:15-25`, `verify_admin_token` `:28-37`, `require_admin` `:40-43`
- `src/storage.py` (lines 1-109) — `TaskStore.load` `:23-30`, `save` `:32-36`, `clear` `:58-62`, `list_tasks` `:65-76`, `render_report` `:79-87`, `export_report` `:90-108`
- `src/stats.py` (lines 1-67) — `average_completion_days` `:45-55`, `summarize` `:58-66`
- `src/cli.py` (lines 1-119, context only) — `build_parser` `:32-63`, `main` `:66-114`
- `src/models.py` (lines 1-78, context only) — `Task.__post_init__` `:31-46`, `Task.from_dict` `:60-77`, `PRIORITY_RANK` `:12`
- `requirements.txt` (1 line)
- `tests/test_cli.py:59`, `tests/test_storage.py:63` (referenced via grep, for fix-coverage confirmation only)
- `HOWTORUN.md:44-48`, `:78`, `:178`, `:192` (referenced via grep, for documented usage of the token)

**Commands run:**

- `python3 -m pytest -q` → `32 passed` (independent confirmation of the fix summary's claim)
- `git diff --stat -- requirements.txt src/` → empty (files are untracked in this repo state)
- `git status --porcelain src/` → all `??`, confirming **no source file was modified by this review**
- Grep for `verify_admin_token|expected_token|require_admin|export_report|TASKTRACKER_ADMIN_TOKEN|hw4-admin-secret|DEFAULT_ADMIN_TOKEN` across the repo excluding `context/bugs/**`
- Export containment probes T1-T7 under `/tmp/secver` (relative traversal, absolute path, symlinked
  file, symlinked directory, nested legitimate name, caller-chosen `--export-dir`, empty and `.` names),
  followed by `ls`/`find` to confirm nothing escaped
- Admin auth probes A1-A7 under `/tmp/secver` (unset env var, empty env var, wrong token, absent
  `--token`, one-character token, whitespace-only token, and a `grep -c` over combined stdout+stderr
  for both the expected and supplied token values)
- Store-loading probes S1-S5 under `/tmp/secver` (non-JSON text, binary file, wrongly typed `id`,
  arbitrary store path, resulting file mode)
- Process-table probe P1 (`ps -o pid=,args=` against a backgrounded process carrying `--token`)
- Brute-force cost probe P2 (`verify_admin_token` against a deliberately weak `TASKTRACKER_ADMIN_TOKEN`)
- `rm -rf /tmp/secver` — all scratch state removed; `data/` and the repository working tree were never
  written to
