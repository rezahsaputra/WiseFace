# Self-Hosted Face Compare API

A stateless, self-hosted **drop-in replacement for the Face++ Compare API**. It
accepts two images, detects and embeds a face in each (Facenet512 via DeepFace),
and returns a `confidence` score plus calibrated `thresholds` — mirroring the
Face++ Compare request/response contract so the existing attendance system only
needs an endpoint + credential swap.

It has **no concept of employees, enrollment, or attendance**, and never
persists images. See [`PRD-self-hosted-face-recognition-attendance (1).md`](PRD-self-hosted-face-recognition-attendance%20(1).md)
for the full product spec.

## Architecture

```
Caller ──HTTPS──> Nginx (TLS, rate limit) ──> API (FastAPI + Gunicorn, 10 workers, Facenet512)
                                                  │  metrics
                                                  ▼
                                            Prometheus ──> Grafana dashboard
```

Single-host Docker Compose deployment. A lightweight SQLite database (WAL mode,
shared by the `api` and `admin` services) holds API-key credentials and per-request
usage logs; live metrics still flow to Prometheus. RAM is the binding constraint,
so every container has an explicit `mem_limit`.

| Service | Image | Mem cap | Purpose |
|---|---|---|---|
| `api` | built from `app/` | 25 GB | Face compare + `/metrics` |
| `admin` | built from `admin/` | 256 MB | Admin panel: API-key management + usage records |
| `nginx` | nginx:1.27-alpine | 256 MB | TLS termination, rate limiting |
| `prometheus` | prom/prometheus:v2.55.1 | 1 GB | Metrics storage (30d retention) |
| `grafana` | grafana:11.4.0 | 512 MB | Usage/monitoring dashboard |

## Quickstart

> Full step-by-step setup, hardware sizing, and troubleshooting:
> **[INSTALLATION.md](INSTALLATION.md)**.

```bash
# 1. Configure
cp .env.example .env
#   edit .env: set real API_CREDENTIALS and GRAFANA_ADMIN_PASSWORD

# 2. TLS cert for Nginx (self-signed for dev/internal)
bash scripts/gen-certs.sh          # or: pwsh scripts/gen-certs.ps1 on Windows

# 3. Build & run
docker compose up -d --build

# 4. Verify
curl -k https://localhost/health
```

- Compare endpoint: `https://localhost/facepp/v3/compare` (alias: `/v3/compare`)
- Grafana: `http://localhost:3001` (login from `.env`)
- Admin panel: `http://localhost:8080` (login with `ADMIN_USER` / `ADMIN_PASSWORD`) — generate/revoke API keys and view usage by hour/day/month/year. Keep this port firewalled; do not expose it to the internet.

> First container start downloads the Facenet512 weights into the
> `deepface_weights` volume; subsequent restarts reuse them.

## API contract

`POST /facepp/v3/compare` (form-data, multipart, or query) — same fields as
Face++ Compare:

| Param | Notes |
|---|---|
| `api_key`, `api_secret` | Validated against the config credential list |
| `image_url1` / `image_file1` / `image_base64_1` | Image 1 (one of) |
| `image_url2` / `image_file2` / `image_base64_2` | Image 2 (one of) |
| `face_token1` / `face_token2` | **Not implemented in v1** (PRD §5.1) |

Per-slot precedence when multiple are supplied: **`image_file` > `image_base64` > `image_url`** (identical to Face++).

**Success (200):**
```json
{
  "confidence": 87.42,
  "thresholds": { "1e-3": 62.327, "1e-4": 69.101, "1e-5": 73.975 },
  "request_id": "f1c2...",
  "time_used": 412
}
```

**Error (4xx/5xx):**
```json
{ "error_message": "NO_FACE_DETECTED", "request_id": "f1c2...", "time_used": 38 }
```

Error codes: `AUTHENTICATION_ERROR`, `MISSING_ARGUMENTS`, `INVALID_IMAGE`,
`IMAGE_ERROR_FAILED_TO_DOWNLOAD`, `IMAGE_FILE_TOO_LARGE`, `NO_FACE_DETECTED`,
`INTERNAL_ERROR`.

> ⚠️ **Thresholds are recalibrated, not Face++'s numbers.** They are
> structurally compatible but **not** numerically interchangeable. Any caller
> logic that hardcodes a Face++ threshold value must be re-pointed at these
> values once Milestone 0 calibration is done.

### Example

```bash
curl -k -X POST https://localhost/facepp/v3/compare \
  -F api_key=YOUR_KEY -F api_secret=YOUR_SECRET \
  -F image_file1=@person_live.jpg \
  -F image_file2=@person_reference.jpg
```

## Configuration

All settings are environment variables (see `.env.example`). Key ones:

| Var | Default | Meaning |
|---|---|---|
| `API_CREDENTIALS` / `API_CREDENTIALS_FILE` | — | Caller credentials (inline JSON or file path) |
| `MODEL_NAME` | `Facenet512` | Approved backends: `Facenet512`, `SFace`, `Dlib` |
| `DETECTOR_BACKEND` | `opencv` | `opencv` (fast) / `retinaface` / `mtcnn` (accurate) |
| `CONFIDENCE_SCALE`, `CONFIDENCE_OFFSET` | `100.0`, `0.0` | Similarity→confidence affine calibration (placeholder) |
| `THRESHOLD_1E_3/4/5` | placeholder | Threshold tiers (recompute in Milestone 0) |
| `GUNICORN_WORKERS` | `10` | RAM-derived worker ceiling on the 16 GB host |
| `MAX_IMAGE_DIM` | `1024` | Downscale longest side before detection (px); 0 disables |
| `INFERENCE_CONCURRENCY` | `1` | Compares per worker. Keep 1 — the OpenCV detector isn't thread-safe |
| `MAX_CONCURRENT_REQUESTS` | `0` | Per-worker load-shed cap → 403 `CONCURRENCY_LIMIT_EXCEEDED`; 0 disables |

## Testing

The test suite mocks the recognition engine, so it runs **without** TensorFlow:

```bash
pip install -r app/requirements-dev.txt
pytest
```

Covered: image precedence resolution, base64/file/url decoding, similarity &
confidence math, full API contract (auth, error shapes, precedence, metrics),
and confirmation that no employee/identity parameter is ever required.

For load/burst testing (Milestone 0/3), point k6 or Locust at the confirmed
burst rate (~10 req/sec worst case) and watch the Grafana latency panels.

## Operational notes

- **Windows host (PRD §9.3):** if not on Ubuntu, set Windows Update **Active
  Hours to 06:00–22:00** so a forced reboot can't land during the 09:00 / 18:00
  burst windows. Configure Docker/WSL2 to auto-start on boot.
- **Memory (PRD §9.4):** `mem_limit`s are enforced in `docker-compose.yml`.
  Validate they hold under load (`docker stats`) before trusting them.
- **Single container by design (PRD §5):** updates incur ~30–60s planned
  downtime on restart; acceptable for this single-server deployment.
- **Data handling (PRD §2):** images are processed in memory and discarded;
  metrics/logs contain no image data and no identity data.

## Project layout

```
app/                 FastAPI service
  main.py            routes (/facepp/v3/compare, /v3/compare, /health, /metrics)
  config.py          settings + credential loading
  image_loader.py    url/file/base64 resolution + precedence
  face_engine.py     DeepFace/Facenet512 wrapper, similarity, confidence
  compare.py         pipeline orchestration
  metrics.py         Prometheus instrumentation (multiprocess-safe)
  errors.py          Face++-shaped error model
  gunicorn_conf.py   worker tuning (10 workers, OMP_NUM_THREADS=1)
  Dockerfile
  tests/             pytest suite (engine mocked, no TF required)
nginx/               reverse proxy config + certs
prometheus/          scrape config
grafana/             datasource + dashboard provisioning
scripts/             cert generation helpers
docker-compose.yml
```

## Status vs. PRD milestones

This repo implements **Milestone 1 (Core Service Development)**: the compare
endpoint, metrics, Grafana dashboard, Docker Compose with `mem_limit`, and the
unit/contract test suite. Calibration values (`CONFIDENCE_*`, `THRESHOLD_*`) are
placeholders pending the **Milestone 0** FAR/FRR validation set.

## License

Released under the [MIT License](LICENSE).
