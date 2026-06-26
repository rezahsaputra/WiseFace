# Installation Guide

This guide walks through deploying the WiseFace Face Compare API stack on a
single host with Docker Compose: the `api` service, the `admin` panel, Nginx
(TLS), and the Prometheus + Grafana monitoring pair.

> For a 30-second overview see the [Quickstart in the README](README.md#quickstart).
> This document is the long-form version with prerequisites, hardware sizing,
> first-run steps, and troubleshooting.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **Docker Engine** 24+ | [Install Docker](https://docs.docker.com/engine/install/) |
| **Docker Compose v2** | Bundled with modern Docker as `docker compose` (no hyphen) |
| **OpenSSL** | Only for generating a self-signed dev cert (step 3) |
| **Git** | To clone the repository |
| **CPU** | x86-64. The image is **CPU-only** (no GPU/CUDA needed) |
| **RAM** | See sizing below — RAM is the binding constraint |
| **Disk** | ~6 GB for images + model weights |

This stack runs entirely on CPU. The `api` Dockerfile deliberately strips the
GPU TensorFlow build and installs `tensorflow-cpu`.

### Hardware sizing

Each Gunicorn worker loads its own Facenet512 model (~800 MB). The default
config targets a large server (Xeon, 24 vCPU, 128 GB RAM) with **20 workers**:

| Workers | Approx. RAM for `api` | Suitable host |
|---|---|---|
| 20 (default) | ~25 GB | 24 vCPU / 128 GB server |
| 4 | ~5 GB | small VM / dev laptop |
| 2 | ~3 GB | minimal test box |

To run on a smaller machine, lower `GUNICORN_WORKERS` and the `api` `mem_limit`
in `docker-compose.yml` — see [step 6](#6-running-on-a-smaller-machine).

### Supported OS

- **Linux (recommended)** — Ubuntu 24.04 is the reference target.
- **Windows** — works via Docker Desktop / WSL2. If this is a production host,
  set Windows Update **Active Hours** wide enough that a forced reboot can't
  land during your traffic peaks, and configure Docker/WSL2 to auto-start on
  boot.

---

## 2. Clone and configure

```bash
git clone https://github.com/rezahsaputra/WiseFace.git
cd WiseFace

cp .env.example .env
```

Open `.env` and set, at minimum:

| Variable | What to set |
|---|---|
| `API_CREDENTIALS` | JSON array of caller credentials. **Seeds the database on first boot.** Example below. |
| `ADMIN_USER` / `ADMIN_PASSWORD` | Login for the admin panel (port 8080). Set a strong password. |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | Login for Grafana (port 3001). |
| `DEMO_API_KEY` / `DEMO_API_SECRET` | Only needed if you run the optional demo profile. |

Example `API_CREDENTIALS` (one caller):

```env
API_CREDENTIALS=[{"api_key":"my-app-key","api_secret":"my-app-secret","client":"attendance-system"}]
```

> **How credentials work:** on the very first start, if the `api_keys` table is
> empty, the API seeds it from `API_CREDENTIALS`. After that, the database is the
> source of truth — manage keys through the **admin panel**, not this variable.
> Editing `API_CREDENTIALS` later has no effect unless the table is empty again.

`.env` is git-ignored; never commit real credentials.

---

## 3. Generate a TLS certificate (for Nginx)

Nginx terminates TLS and expects `nginx/certs/server.crt` and
`nginx/certs/server.key`. Generate a self-signed pair for dev/internal use:

```bash
# Linux / macOS / Git Bash
bash scripts/gen-certs.sh
```

```powershell
# Windows PowerShell
pwsh scripts/gen-certs.ps1
```

This writes a cert valid for `localhost`, `127.0.0.1`, and
`face-compare.internal`. **For production, replace these files with a
certificate from your internal CA.**

---

## 4. Build and run

```bash
docker compose up -d --build
```

The **first** build downloads the full ML stack and the **first** container
start downloads the Facenet512 weights into the `deepface_weights` volume.

> On a slow connection the initial build can take a long time (the ML stack is
> ~500 MB of wheels). This is normal — let it finish; don't kill it midway.

Subsequent starts reuse the cached image and weights and come up in seconds.

---

## 5. Verify

```bash
# API health (direct)
curl http://localhost:8000/health

# API health (through Nginx + TLS; -k accepts the self-signed cert)
curl -k https://localhost/health
```

Default exposed ports:

| Service | URL | Login |
|---|---|---|
| API (compare) | `https://localhost/facepp/v3/compare` (or `http://localhost:8000`) | `api_key` + `api_secret` |
| Admin panel | `http://localhost:8080` | `ADMIN_USER` / `ADMIN_PASSWORD` |
| Grafana | `http://localhost:3001` | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` |
| Prometheus | internal only (not published) | — |

> **Firewall the admin panel and Grafana** if the host is reachable from
> untrusted networks. Only the compare endpoint (via Nginx) is meant to be
> reachable by callers.

Send a real compare request:

```bash
curl -k -X POST https://localhost/facepp/v3/compare \
  -F api_key=my-app-key -F api_secret=my-app-secret \
  -F image_file1=@person_live.jpg \
  -F image_file2=@person_reference.jpg
```

### First steps in the admin panel

1. Open `http://localhost:8080`, log in with `ADMIN_USER` / `ADMIN_PASSWORD`.
2. **API Keys** tab → *Generate Key Baru* → give it a label. The new
   `api_key` + `api_secret` are shown **once** — copy them immediately.
3. **Penggunaan** tab → view request volume, success rate, and latency by
   hour / day / month / year.

New keys become usable within ~30 seconds (the per-worker credential cache TTL).

---

## 6. Running on a smaller machine

Edit `docker-compose.yml`, `api` service:

```yaml
  api:
    environment:
      GUNICORN_WORKERS: "4"   # was 20
    mem_limit: 6g             # was 25g
    mem_reservation: 4g       # was 18g
```

Then rebuild: `docker compose up -d --build api`. Fewer workers means lower peak
throughput but the same correctness.

---

## 7. Optional: stakeholder demo UI

A Streamlit demo (not started by default) lets non-technical users try the
compare flow:

```bash
# Set DEMO_API_KEY / DEMO_API_SECRET in .env first (use a real key)
docker compose --profile demo up -d api demo
# then open http://localhost:8501
```

---

## 8. Day-2 operations

```bash
docker compose ps                 # service status
docker compose logs -f api        # follow API logs
docker compose logs -f admin      # follow admin logs
docker stats                      # live memory/CPU (validate mem_limits)

docker compose restart api        # restart one service
docker compose down               # stop everything (keeps volumes/data)

# Update to the latest code
git pull
docker compose up -d --build
```

Named volumes that persist across restarts:

| Volume | Holds |
|---|---|
| `wiseface_data` | SQLite DB — API keys + usage logs |
| `deepface_weights` | Facenet512 model weights |
| `prometheus_data` | metrics (30-day retention) |
| `grafana_data` | Grafana dashboards/state |

### Resetting the database

```bash
docker compose down
docker volume rm wiseface_wiseface_data   # prefix is the compose project name
docker compose up -d --build
```

On the next start the empty `api_keys` table is re-seeded from
`API_CREDENTIALS`.

---

## 9. Troubleshooting

**`sqlite3.OperationalError: unable to open database file`**
The `wiseface_data` volume was created with wrong ownership (e.g. from an older
image where `/data` wasn't owned by the `app` user). Recreate it:
`docker compose down && docker volume rm wiseface_wiseface_data && docker compose up -d --build`.

**First build is extremely slow / appears stuck**
It's downloading ~500 MB of ML wheels. Let it run. If your network is flaky, pip
is configured to retry; don't cancel the build.

**Browser/curl warns about the TLS certificate**
Expected with the self-signed dev cert. Use `curl -k`, or install a cert from
your internal CA into `nginx/certs/`.

**A newly generated API key returns `AUTHENTICATION_ERROR` for a few seconds**
The API caches credentials per worker for ~30 seconds. Wait and retry.

**`NO_FACE_DETECTED` on valid photos**
Try a more accurate detector: set `DETECTOR_BACKEND=retinaface` (or `mtcnn`) in
`.env` and `docker compose up -d api`. Slower but better on hard angles/lighting.

---

## 10. Running the test suite

The tests mock the recognition engine, so they run **without** TensorFlow:

```bash
pip install -r app/requirements-dev.txt
pytest
```

See the [README](README.md#testing) for what's covered.
