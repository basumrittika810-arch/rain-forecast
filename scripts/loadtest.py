"""Gentle stepped load test of the Vaanam website and API (D-034).

Each simulated user repeats one "visit" like a farmer's:
  - fetch the 8 page files (in parallel, as a browser does),
  - search twice (a few letters, then the full name),
  - 20 % of visits: a misspelt search; 30 %: a "use my location" lookup,
  - fetch one forecast,
  - pause 1-3 s before the next visit.
The number of users steps up (default 5, 10, 20, 35), 20 s per step.
Stops early if more than 5 % of requests fail or the slowest 5 % take over 20 s.
Errors are split into "my side" (the test machine could not connect) and server errors/timeouts.

All users share one pool of at most 60 connections. Without this, the test machine itself ran out of
name lookups (getaddrinfo failed) at 20 users and the failures were wrongly counted against the server.

Usage:  python scripts/loadtest.py [--base URL] [--steps 5,10,20,35] [--seconds 20]
Only run it against a server you are allowed to load. Needs httpx (already used by the tests).
"""
import argparse
import asyncio
import collections
import random
import statistics
import time

import httpx

LIVE = "https://rain-forecast-api-qii4.onrender.com"
TIMEOUT = 90
STOP_ERROR_SHARE = 0.05
STOP_P95_SECONDS = 20
STATIC = ["/", "/app.js", "/style.css", "/icon.svg", "/scene-rain.svg", "/scene-fields.svg",
          "/fonts/baloo2-700-latin.woff2", "/fonts/arima-700-vaanam.woff2"]
PLACES = [("me", "melur", 10.03241, 78.3393), ("than", "thanjavur", 10.787, 79.1378),
          ("oo", "ooty", 11.4102, 76.695), ("mad", "madurai", 9.919, 78.11953),
          ("tir", "tirunelveli", 8.7139, 77.7567), ("che", "chennai", 13.08784, 80.27847)]
KINDS = ("forecast", "search", "misspelt search", "nearest (GPS)", "page files")

results = []                        # (step, kind, seconds, ok)
errkinds = collections.Counter()


async def call(client, step, kind, url, params=None):
    t = time.perf_counter()
    try:
        r = await client.get(url, params=params)
        ok = r.status_code == 200
        if not ok:
            errkinds[f"server {r.status_code}"] += 1
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        ok = False
        errkinds[f"my side: {type(e).__name__}"] += 1
    except Exception as e:  # noqa: BLE001 - any other failure counts against the server
        ok = False
        errkinds[f"server/timeout: {type(e).__name__}"] += 1
    results.append((step, kind, time.perf_counter() - t, ok))


async def visit(client, step):
    typed, full, lat, lon = random.choice(PLACES)
    await asyncio.gather(*(call(client, step, "page files", u) for u in STATIC))
    await call(client, step, "search", "/api/places", {"q": typed})
    await call(client, step, "search", "/api/places", {"q": full})
    if random.random() < 0.2:
        await call(client, step, "misspelt search", "/api/places", {"q": full[:-2] + "xu"})
    if random.random() < 0.3:
        await call(client, step, "nearest (GPS)", "/api/places/nearest", {"lat": lat + 0.01, "lon": lon})
    await call(client, step, "forecast", "/api/forecast", {"lat": lat, "lon": lon})
    await asyncio.sleep(random.uniform(1, 3))   # reading time before the next visit


async def user(client, step, stop):
    while time.monotonic() < stop:
        await visit(client, step)


def _p(sorted_times, q):
    return sorted_times[min(len(sorted_times) - 1, int(q * len(sorted_times)))]


def summary(step, seconds):
    rows = [r for r in results if r[0] == step]
    t = sorted(r[2] for r in rows)
    errs = sum(not r[3] for r in rows)
    visits = sum(1 for r in rows if r[1] == "forecast")
    print(f"{step:3d} users | {len(rows):5d} requests, {visits:4d} visits ({visits / seconds * 60:5.0f}/min) | "
          f"median {statistics.median(t):5.2f}s  p95 {_p(t, .95):5.2f}s  max {t[-1]:5.2f}s | "
          f"errors {errs} ({errs / len(rows):.1%})", flush=True)
    for kind in KINDS:
        k = sorted(r[2] for r in rows if r[1] == kind)
        if k:
            print(f"            {kind:16s} median {statistics.median(k):5.2f}s  p95 {_p(k, .95):5.2f}s  (n={len(k)})",
                  flush=True)
    print(f"            error kinds so far: {dict(errkinds)}", flush=True)
    return errs / len(rows), _p(t, .95)


async def main(base, steps, seconds):
    limits = httpx.Limits(max_connections=60, max_keepalive_connections=60)
    async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT, limits=limits,
                                 headers={"User-Agent": "vaanam-loadtest"}) as client:
        t = time.perf_counter()
        r = await client.get("/api/status")   # also wakes a sleeping free server before measuring
        print(f"warm-up: {r.status_code} in {time.perf_counter() - t:.1f}s", flush=True)
        for step in steps:
            stop = time.monotonic() + seconds
            await asyncio.gather(*(user(client, step, stop) for _ in range(step)))
            err, p95 = summary(step, seconds)
            if err > STOP_ERROR_SHARE or p95 > STOP_P95_SECONDS:
                print(f"STOPPED at {step} users (errors {err:.1%}, p95 {p95:.1f}s)")
                break
        r = await client.get("/api/status")
        print(f"after test: status {r.status_code}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=LIVE, help="site to test (default: the live site)")
    ap.add_argument("--steps", default="5,10,20,35", help="users per step, comma-separated")
    ap.add_argument("--seconds", type=int, default=20, help="length of each step in seconds")
    a = ap.parse_args()
    asyncio.run(main(a.base, [int(s) for s in a.steps.split(",")], a.seconds))
