"""Timed pipeline runs (D-033) and the saved load test (D-034)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")


def _crons():
    return re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', WORKFLOW, flags=re.M)


def test_runs_every_two_hours_at_17_past_from_0817_to_2017_utc():
    assert _crons() == ["17 8-20/2 * * *"]


def test_no_run_on_the_hour_or_half_hour():
    # GitHub is busiest at :00 and :30; timed runs there are more likely to be late or dropped.
    for cron in _crons():
        minute = cron.split()[0]
        assert minute not in ("0", "30")


def test_manual_start_still_available():
    assert "workflow_dispatch:" in WORKFLOW
    assert "simulate_failure:" in WORKFLOW


def test_load_test_script_saved_and_has_stop_rule():
    src = (ROOT / "scripts" / "loadtest.py").read_text(encoding="utf-8")
    ast.parse(src)
    assert "--base" in src and "--steps" in src
    assert "0.05" in src and "20" in src   # stops early on >5 % errors or p95 > 20 s


def test_load_test_results_saved():
    txt = (ROOT / "docs" / "inspection" / "loadtest_20261113.txt").read_text(encoding="utf-8")
    for needed in ("35 users", "errors 0", "getaddrinfo"):
        assert needed in txt
