"""
monitored_run — minimal instrumentation helper for pysdk runner scripts.

Records each execution as a row in xerenity.collector_runs so that the
centralized monitor (xerenity-fe /admin/monitor + Teams alert dispatcher)
can track scripts living in this repo the same way it tracks the
run_collect_*.py scripts in xerenity-dm.

This is a deliberately small stand-alone module so it can wrap any pysdk
runner without depending on xerenity-dm's data_collectors.monitoring
package (which is not installable here).

Usage:

    from src.monitoring import monitored_run

    if __name__ == "__main__":
        with monitored_run("compute_marks"):
            main()

Best-effort design: a broken DB never blocks the wrapped script. If the
INSERT/UPDATE fails, the wrapper logs to stderr and continues; the
script's own exit code remains the source of truth.

Env vars (required only when running against the real DB):
    XTY_URL           Supabase project URL (https://<ref>.supabase.co)
    XTY_TOKEN         Supabase anon/publishable key
    COLLECTOR_BEARER  JWT for the `collector` role (write access)

GitHub Actions auto-populated env vars are picked up automatically:
    GITHUB_SERVER_URL / GITHUB_REPOSITORY / GITHUB_RUN_ID / GITHUB_WORKFLOW
to fill gh_run_url / gh_workflow / gh_run_id on the run row.
"""

from __future__ import annotations

import os
import sys
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import requests


_SUPABASE_URL = os.getenv("XTY_URL")
_SUPABASE_KEY = os.getenv("XTY_TOKEN")
_COLLECTOR_BEARER = os.getenv("COLLECTOR_BEARER")
_RUNS_TABLE = "collector_runs"

_ERROR_MESSAGE_MAX = 500
_TRACEBACK_TAIL_MAX = 4000


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gh_context() -> dict:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    workflow = os.environ.get("GITHUB_WORKFLOW", "")
    run_url = (
        f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else None
    )
    return {
        "gh_run_url": run_url,
        "gh_workflow": workflow or None,
        "gh_run_id": run_id or None,
    }


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "apikey": _SUPABASE_KEY or "",
        "Authorization": f"Bearer {_COLLECTOR_BEARER or _SUPABASE_KEY or ''}",
        "Content-Type": "application/json",
        "Accept-Profile": "xerenity",
        "Content-Profile": "xerenity",
    })
    return s


def _open_run(name: str) -> str | None:
    """INSERT a running row and return its id. Returns None on failure."""
    if not _SUPABASE_URL:
        return None
    run_id = str(uuid.uuid4())
    payload = {
        "id": run_id,
        "collector_name": name,
        "started_at": _utc_iso(),
        "status": "running",
        "metadata": {"runner": "pysdk.src.monitoring"},
        **_gh_context(),
    }
    try:
        r = _session().post(
            f"{_SUPABASE_URL}/rest/v1/{_RUNS_TABLE}",
            json=[payload],
            headers={"Prefer": "return=minimal"},
        )
        if r.status_code not in (200, 201):
            print(
                f"[monitored_run] open failed: {r.status_code} {r.text[:200]}",
                file=sys.stderr,
            )
            return None
        return run_id
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f"[monitored_run] open error: {e}", file=sys.stderr)
        return None


def _close_run(run_id: str, **fields) -> None:
    if not _SUPABASE_URL or not run_id:
        return
    fields["finished_at"] = _utc_iso()
    try:
        r = _session().patch(
            f"{_SUPABASE_URL}/rest/v1/{_RUNS_TABLE}?id=eq.{run_id}",
            json=fields,
        )
        if r.status_code not in (200, 204):
            print(
                f"[monitored_run] close failed: {r.status_code} {r.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:  # noqa: BLE001
        print(f"[monitored_run] close error: {e}", file=sys.stderr)


@contextmanager
def monitored_run(name: str):
    """
    Context manager that records the wrapped block as a single execution
    in xerenity.collector_runs. Exceptions raised inside the block are
    captured (status=failed + truncated traceback) and re-raised so the
    script's own exit code is preserved.
    """
    run_id = _open_run(name)

    try:
        yield run_id
    except SystemExit as e:
        # Treat clean exit codes as success, non-zero as failed.
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if code == 0:
            _close_run(run_id, status="success", exit_code=0)
        else:
            _close_run(
                run_id,
                status="failed",
                exit_code=code,
                error_message=f"SystemExit({e.code})"[:_ERROR_MESSAGE_MAX],
            )
        raise
    except Exception as e:
        tb = traceback.format_exc()
        _close_run(
            run_id,
            status="failed",
            exit_code=1,
            error_message=str(e)[:_ERROR_MESSAGE_MAX] or e.__class__.__name__,
            error_traceback=tb[-_TRACEBACK_TAIL_MAX:],
        )
        raise
    else:
        _close_run(run_id, status="success", exit_code=0)
