"""Burst load test for the Face++-compatible compare API.

Simulates a clock-in/out rush: fires TOTAL real compare requests (full
Facenet512 inference, not mocked) against the running service, holding at most
CONCURRENCY in flight at once, and reports throughput + latency percentiles +
an outcome breakdown.

Run inside the face-compare-api image (which already has httpx), with the repo
mounted at /work:

    docker run --rm --network <net> \
      -e TARGET_URL=http://facecmp-api:8000/facepp/v3/compare \
      -e API_KEY=... -e API_SECRET=... -e TOTAL=1000 -e CONCURRENCY=20 \
      -v <repo>:/work -w /work --entrypoint python \
      face-compare-api:1.0.0 scripts/burst_loadtest.py
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from collections import Counter

import httpx

URL = os.environ.get("TARGET_URL", "http://localhost:8000/facepp/v3/compare")
TOTAL = int(os.environ.get("TOTAL", "1000"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "20"))
KEY = os.environ.get("API_KEY", "")
SECRET = os.environ.get("API_SECRET", "")
IMG1 = os.environ.get("IMG1", "/work/testdata/face1.jpg")
IMG2 = os.environ.get("IMG2", "/work/testdata/face2.jpg")
CLIENT_TIMEOUT = float(os.environ.get("CLIENT_TIMEOUT", "60"))
# KEEPALIVE=0 opens a fresh connection per request ("Connection: close"), which
# models many independent clients and lets gunicorn spread load across workers,
# rather than one client pinning a few keepalive connections to a few workers.
KEEPALIVE = os.environ.get("KEEPALIVE", "1") != "0"
# VERIFY=0 skips TLS verification — needed when driving the nginx endpoint with
# its self-signed dev cert.
VERIFY = os.environ.get("VERIFY", "1") != "0"

with open(IMG1, "rb") as f:
    B1 = f.read()
with open(IMG2, "rb") as f:
    B2 = f.read()


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
    return s[k]


async def one(client: httpx.AsyncClient, sem: asyncio.Semaphore,
              latencies: list[float], outcomes: Counter) -> None:
    files = {
        "image_file1": ("a.jpg", B1, "image/jpeg"),
        "image_file2": ("b.jpg", B2, "image/jpeg"),
    }
    data = {"api_key": KEY, "api_secret": SECRET}
    headers = {} if KEEPALIVE else {"Connection": "close"}
    async with sem:
        t0 = time.perf_counter()
        try:
            r = await client.post(URL, data=data, files=files, headers=headers)
            dt = time.perf_counter() - t0
            latencies.append(dt)
            if r.status_code == 200:
                outcomes["200 success"] += 1
            else:
                label = f"HTTP {r.status_code}"
                try:
                    label += f" / {r.json().get('error_message', '?')}"
                except Exception:
                    pass
                outcomes[label] += 1
        except httpx.TimeoutException:
            latencies.append(time.perf_counter() - t0)
            outcomes["client timeout"] += 1
        except Exception as exc:  # noqa: BLE001
            latencies.append(time.perf_counter() - t0)
            outcomes[f"client error: {type(exc).__name__}"] += 1


async def main() -> int:
    print(f"target      : {URL}")
    print(f"total       : {TOTAL}")
    print(f"concurrency : {CONCURRENCY}")
    print(f"images      : {IMG1} ({len(B1)} B)  vs  {IMG2} ({len(B2)} B)")
    print("running...", flush=True)

    latencies: list[float] = []
    outcomes: Counter = Counter()
    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(
        max_connections=CONCURRENCY,
        max_keepalive_connections=CONCURRENCY if KEEPALIVE else 0,
    )
    timeout = httpx.Timeout(CLIENT_TIMEOUT)

    wall0 = time.perf_counter()
    async with httpx.AsyncClient(limits=limits, timeout=timeout, verify=VERIFY) as client:
        tasks = [asyncio.create_task(one(client, sem, latencies, outcomes))
                 for _ in range(TOTAL)]
        await asyncio.gather(*tasks)
    wall = time.perf_counter() - wall0

    ok = outcomes.get("200 success", 0)
    print("\n========== RESULTS ==========")
    print(f"wall clock        : {wall:8.2f} s")
    print(f"throughput        : {TOTAL / wall:8.2f} req/s")
    print(f"success           : {ok}/{TOTAL} ({100.0 * ok / TOTAL:.1f}%)")
    print("\noutcome breakdown :")
    for label, n in outcomes.most_common():
        print(f"  {n:6d}  {label}")
    print("\nlatency (s)       :")
    print(f"  min   {min(latencies):7.3f}")
    print(f"  p50   {pct(latencies, 50):7.3f}")
    print(f"  p90   {pct(latencies, 90):7.3f}")
    print(f"  p95   {pct(latencies, 95):7.3f}")
    print(f"  p99   {pct(latencies, 99):7.3f}")
    print(f"  max   {max(latencies):7.3f}")
    print(f"  mean  {statistics.mean(latencies):7.3f}")
    print("=============================")
    return 0 if ok == TOTAL else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
