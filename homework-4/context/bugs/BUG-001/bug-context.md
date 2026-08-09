# BUG-001 — Task Tracker: stats crash, wrong priority order, admin/export hardening

| Field | Value |
|---|---|
| **Bug ID** | BUG-001 |
| **Reported by** | QA (internal), after the 1.0.0 smoke run |
| **Reported on** | 2026-08-10 |
| **Severity** | High (one crash, one wrong result, one security concern) |
| **Component** | `homework-4/` Task Tracker CLI (`python -m src.cli`) |
| **Version** | `src.__version__ == "1.0.0"` |
| **Test command** | `cd homework-4 && python3 -m pytest` |
| **Run command** | `cd homework-4 && python3 -m src.cli --help` |

## Environment

- macOS / Linux, Python 3.11+
- No external services; the app stores tasks in a JSON file (`--store`, default `data/tasks.json`)
- Only test dependency: `pytest` (`requirements.txt`)

## Reported symptoms

### S1 — `stats` crashes on a store with no completed tasks

The `stats` command dies with a traceback instead of printing the summary. It only works once at
least one task has been completed, which means a fresh install can never show statistics.

Reproduction:

```bash
cd homework-4
python3 -m src.cli --store /tmp/s1.json add "Anything"
python3 -m src.cli --store /tmp/s1.json stats
# ZeroDivisionError: division by zero
```

Expected: the command prints the JSON summary. A collection with no completed tasks has no average
completion time — the summary should report a neutral value for that field instead of crashing.
QA also notes that `completion_rate` already handles the empty case correctly, so the two functions
disagree about how "no data" is represented.

### S2 — `list --sort priority` returns the wrong order

Sorting by priority produces alphabetical order, not severity order. `urgent` tasks appear last,
which is the opposite of what the flag is for.

Reproduction:

```bash
cd homework-4
for p in low urgent medium high; do
  python3 -m src.cli --store /tmp/s2.json add "task-$p" --priority "$p"
done
python3 -m src.cli --store /tmp/s2.json list --sort priority
# observed: high, low, medium, urgent
# expected: urgent, high, medium, low
```

Expected: tasks are ordered from most to least severe. The severity order is already declared
somewhere in the model layer; the listing code does not appear to use it. Ties should keep a stable,
predictable secondary order.

### S3 — security review flagged the admin path and the export command

A pre-release review raised two concerns that were never addressed and need a concrete fix:

1. **Admin token handling.** Reviewers could run the destructive `admin clear` command on a machine
   where no admin token had ever been configured, and the rejection message they got back when
   guessing echoed their input. The reviewers asked for: no usable token unless the operator
   configures one, and a token comparison that does not leak information through timing or error
   text.

2. **`export` writes outside its export directory.** A report filename containing `..` segments (or
   an absolute path) escapes the export directory and overwrites arbitrary files:

   ```bash
   cd homework-4
   python3 -m src.cli --store /tmp/s3.json export "../../../../tmp/ESCAPED.txt" --export-dir ./exports
   # observed: file created at /tmp/ESCAPED.txt
   ```

   Expected: filenames that resolve outside the export directory are rejected with a clear error and
   a non-zero exit code; nothing is written.

## Acceptance criteria

- [ ] `stats` succeeds on a store with zero tasks and on a store with no completed tasks.
- [ ] `list --sort priority` returns `urgent → high → medium → low`, with deterministic tie-breaking.
- [ ] `admin clear` is impossible unless an admin token is explicitly configured in the environment.
- [ ] Token comparison is constant-time and error messages do not echo the supplied token.
- [ ] `export` refuses any filename that resolves outside the export directory, writing nothing.
- [ ] The existing suite (32 tests) still passes; no public CLI flags are renamed or removed.

## Out of scope

- Adding a database, network API, or authentication beyond the single admin token.
- Reformatting or restructuring modules that are not required by the fixes.
- Changing the JSON store file format.
