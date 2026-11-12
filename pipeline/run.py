"""One-command pipeline for scheduled runs (GitHub Actions): fetch the newest complete run, publish it,
and build the static site folder that GitHub Pages serves.

  1. Read the currently published latest.json (from GitHub Pages) and seed data/processed/latest.json with it,
     so publish_run's "never replace a newer forecast with an older one" check works on a fresh machine.
     If it cannot be read (other than "not published yet"), stop: never publish blind.
  2. If the newest complete run on ECMWF is not newer than the published one: outcome "unchanged" (no download).
  3. Otherwise fetch + validate (Step 1) and compute + check + publish (Step 2), then copy latest.json into
     the site folder: outcome "published". Any failure raises, so the workflow fails and Pages is not updated.

Usage:
  python -m pipeline.run --published-url https://<user>.github.io/rain-forecast/latest.json --site-dir site
  python -m pipeline.run ... --simulate-failure      (test mode: forces a corrupt download that must be rejected)
"""

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pipeline.fetch import (DATA_ROOT, ecmwf_download, fetch_run, find_latest_complete_run, list_server_steps,
                            run_id)
from pipeline.publish import ATTRIBUTION, publish_run
from pipeline.validate import REAL_GRID

log = logging.getLogger("pipeline.run")


class PublishedFetchError(RuntimeError):
    pass


def published_reader(url: str):
    """Return a function giving the published latest.json text, None if not published yet (HTTP 404)."""
    def read():
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise PublishedFetchError(f"HTTP {e.code} reading {url}") from e
        except urllib.error.URLError as e:
            raise PublishedFetchError(f"cannot reach {url}: {e.reason}") from e
    return read


def _simulated_corrupt_download(init, steps, target):
    target.write_bytes(b"simulated corrupt download (test mode)")


INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rain forecast data</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem;">
<h1>Rain forecast data</h1>
<p>Published forecast run: <strong>{run}</strong> (IST).</p>
<p>Machine-readable file: <a href="latest.json">latest.json</a></p>
<p>{attribution}</p>
</body></html>
"""


def _build_site(processed: Path, site_dir: Path) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(processed / "latest.json", site_dir / "latest.json")
    doc = json.loads((site_dir / "latest.json").read_text(encoding="utf-8"))
    (site_dir / "index.html").write_text(INDEX_HTML.format(run=doc["run"]["init_ist"], attribution=ATTRIBUTION),
                                         encoding="utf-8")
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")


def run_pipeline(data_root: Path = DATA_ROOT, site_dir: Path = Path("site"), now: dt.datetime | None = None,
                 fetch_published=lambda: None, list_steps=list_server_steps, download=ecmwf_download,
                 region=None, grid: dict = REAL_GRID, simulate_failure: bool = False) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    processed = data_root / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    current = None
    text = fetch_published()
    if text is not None:
        try:
            current = dt.datetime.fromisoformat(json.loads(text)["run"]["init_utc"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError) as e:
            raise PublishedFetchError(f"published latest.json is unreadable: {type(e).__name__}: {e}") from e
        (processed / "latest.json").write_text(text, encoding="utf-8")
        log.info("currently published run: %s", run_id(current))
    else:
        log.info("no forecast published yet")

    init = find_latest_complete_run(now, list_steps=list_steps)
    rid = run_id(init)
    log.info("newest complete run on ECMWF: %s", rid)
    if simulate_failure:
        log.warning("TEST MODE: simulating a corrupt download of %s; it must be rejected", rid)
        download = _simulated_corrupt_download
    elif current is not None and init <= current:
        log.info("nothing to do: %s is not newer than the published run", rid)
        return "unchanged"

    run_dir = data_root / "runs" / rid
    if not run_dir.exists():
        run_dir = fetch_run(init, data_root, download=download, grid=grid)
    already = (processed / f"{rid}.json").exists()
    publish_run(run_dir, data_root, region=region, grid=grid)
    if already:
        log.info("%s was already published locally", rid)
        return "unchanged"
    _build_site(processed, site_dir)
    log.info("site folder ready: %s", site_dir)
    return "published"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--published-url", help="URL of the currently published latest.json (GitHub Pages)")
    ap.add_argument("--site-dir", default="site")
    ap.add_argument("--simulate-failure", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stdout)
    simulate = args.simulate_failure or os.environ.get("SIMULATE_FAILURE", "").lower() == "true"
    outcome = run_pipeline(site_dir=Path(args.site_dir),
                           fetch_published=published_reader(args.published_url) if args.published_url else (lambda: None),
                           simulate_failure=simulate)
    log.info("outcome: %s", outcome)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"outcome={outcome}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
