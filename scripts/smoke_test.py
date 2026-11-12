"""Smoke test for a running API (local or deployed). Standard library only.

Usage:
    python scripts/smoke_test.py https://<api-host> [--published-url https://<user>.github.io/rain-forecast/latest.json]
                                 [--max-age-hours 60]

Checks status, one known location (Chennai), dates/times/durations/units/status rules, error responses,
and (optionally) that the API returns exactly what is published. Exit code 0 = all checks passed.
"""

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request

CHENNAI = (13.0825, 80.275)
CHENNAI_GRID = {"lat": 13.0, "lon": 80.25}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def get(url, timeout=120):
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read()), time.perf_counter() - t
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), time.perf_counter() - t


def ts(s):
    return dt.datetime.fromisoformat(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--published-url")
    ap.add_argument("--max-age-hours", type=float, default=60)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    code, s, secs = get(f"{base}/api/status")
    check("status endpoint responds", code == 200, f"HTTP {code}, {secs:.1f} s (first call may include wake-up)")
    check("a forecast is available", s.get("forecast_available") is True, f"last_reload_error={s.get('last_reload_error')}")
    if not s.get("forecast_available"):
        return 1
    check("forecast age within limit", s["age_hours"] <= a.max_age_hours,
          f"{s['age_hours']} h old (run {s['run_init_ist']} IST), limit {a.max_age_hours} h")
    check("quality is ok or partial", s["quality"]["status"] in ("ok", "partial"), json.dumps(s["quality"]))

    code, f, secs = get(f"{base}/api/forecast?lat={CHENNAI[0]}&lon={CHENNAI[1]}")
    check("Chennai forecast responds", code == 200, f"HTTP {code}, {secs * 1000:.0f} ms")
    if code != 200:
        return 1
    check("Chennai snaps to grid point 13.00, 80.25", f["grid_point"] == CHENNAI_GRID, str(f["grid_point"]))
    check("units are mm and mm/h", f["units"]["rain"] == "mm" and f["units"]["rate"] == "mm/h")
    check("ECMWF attribution present", "ECMWF" in f["attribution"] and "CC BY 4.0" in f["attribution"])

    days, ivs, init = f["days"], f["intervals"], ts(f["run"]["init_ist"])
    horizon_end = init + dt.timedelta(hours=f["run"]["horizon_hours"])
    check("11 days and 67 intervals", (len(days), len(ivs)) == (11, 67), f"{len(days)} / {len(ivs)}")
    check("first day starts at run start, is partial (18 h)",
          ts(days[0]["start"]) == init and days[0]["partial"] and days[0]["hours"] == 18)
    check("other days are 24 h, end 23:30 IST",
          all(d["hours"] == 24 and not d["partial"] for d in days[1:]) and
          all(d["end"].endswith("T23:30+05:30") for d in days))
    check("dates are consecutive",
          all(ts(b["date"] + "T00:00") - ts(a["date"] + "T00:00") == dt.timedelta(days=1) for a, b in zip(days, days[1:])))
    check("days and intervals are contiguous",
          all(a["end"] == b["start"] for a, b in zip(days, days[1:])) and
          all(a["end"] == b["start"] for a, b in zip(ivs, ivs[1:])))
    check("intervals span run start -> horizon", ts(ivs[0]["start"]) == init and ts(ivs[-1]["end"]) == horizon_end)
    check("interval hours: 3 up to +144 h, then 6",
          all(i["hours"] == (3 if ts(i["end"]) <= init + dt.timedelta(hours=144) else 6) and
              ts(i["end"]) - ts(i["start"]) == dt.timedelta(hours=i["hours"]) for i in ivs))

    def status_ok(e):
        if e["status"] == "ok":
            return e["mm"] is not None and e["mm"] >= 0 and e["mm"] == e["raw_mm"]
        if e["status"] == "adjusted":
            return e["mm"] == 0 and e["raw_mm"] is not None and e["raw_mm"] < 0
        if e["status"] == "unavailable":
            return e["mm"] is None and e["raw_mm"] is None and bool(e.get("reason"))
        return False
    bad = [e for e in days + ivs if not status_ok(e)]
    check("status rules (ok / adjusted / unavailable never shown as 0)", not bad, f"{len(bad)} violations")
    sums_ok = all(d["raw_mm"] == sum(i["raw_mm"] for i in ivs if d["start"] <= i["start"] and i["end"] <= d["end"])
                  for d in days if d["raw_mm"] is not None and
                  all(i["raw_mm"] is not None for i in ivs if d["start"] <= i["start"] and i["end"] <= d["end"]))
    check("each day equals the sum of its intervals", sums_ok)
    print("      Chennai daily mm:", [(d["date"][5:], None if d["mm"] is None else round(d["mm"], 3)) for d in days])

    if a.published_url:
        _, pub, _ = get(a.published_url)
        stored = pub["points"]["13.00,80.25"]
        check("API values identical to published latest.json",
              f["days"] == stored["days"] and f["intervals"] == stored["intervals"] and f["run"] == pub["run"],
              f"published run {pub['run']['init_utc']}")

    code, e, _ = get(f"{base}/api/forecast?lat=22.5675&lon=88.37")
    check("Kolkata (outside region) -> 404", code == 404, e.get("detail", "")[:80])
    code, _, _ = get(f"{base}/api/forecast?lat=abc&lon=80")
    check("invalid latitude -> 422", code == 422)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
