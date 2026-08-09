"""Baseline tests for the CLI surface."""

from __future__ import annotations

import json

from src.cli import main


def run(capsys, *argv, store=None):
    """Invoke the CLI and return (exit_code, stdout, stderr)."""
    args = (["--store", str(store)] if store else []) + list(argv)
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_add_then_list(capsys, store_path):
    assert run(capsys, "add", "Buy milk", "--priority", "high", store=store_path)[0] == 0
    code, out, _ = run(capsys, "list", store=store_path)
    assert code == 0
    assert "Buy milk" in out
    assert "high" in out


def test_list_on_empty_store(capsys, store_path):
    code, out, _ = run(capsys, "list", store=store_path)
    assert code == 0
    assert "no tasks yet" in out


def test_complete_and_stats(capsys, store_path):
    run(capsys, "add", "Ship it", store=store_path)
    assert run(capsys, "complete", "1", store=store_path)[0] == 0
    code, out, _ = run(capsys, "stats", store=store_path)
    assert code == 0
    payload = json.loads(out)
    assert payload["total"] == 1
    assert payload["completion_rate_pct"] == 100.0


def test_complete_unknown_task_exits_with_code_2(capsys, store_path):
    code, _, err = run(capsys, "complete", "42", store=store_path)
    assert code == 2
    assert "error:" in err


def test_export_writes_file(capsys, tmp_path, store_path):
    run(capsys, "add", "Exported task", store=store_path)
    code, out, _ = run(
        capsys, "export", "report.txt", "--export-dir", str(tmp_path / "out"), store=store_path
    )
    assert code == 0
    assert (tmp_path / "out" / "report.txt").exists()
    assert "report written to" in out


def test_admin_clear_requires_token(capsys, store_path, monkeypatch):
    monkeypatch.setenv("TASKTRACKER_ADMIN_TOKEN", "s3cret-for-test")
    run(capsys, "add", "Doomed task", store=store_path)
    code, _, err = run(capsys, "admin", "clear", "--token", "wrong", store=store_path)
    assert code == 3
    assert "forbidden:" in err
    code, out, _ = run(capsys, "admin", "clear", "--token", "s3cret-for-test", store=store_path)
    assert code == 0
    assert "cleared 1 task(s)" in out
