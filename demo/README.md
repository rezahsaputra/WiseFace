# WiseFace Demo UI (Streamlit)

A small stakeholder-facing web app to try the face-compare service: upload (or
pick sample) two face images, click **Bandingkan Wajah**, and see the confidence
score, match verdict, latency, and the raw API response.

Light mode only, DCT web palette, no emojis (per the project design rules).

## Run

From the repository root (the `api` service must be running):

```bash
docker compose --profile demo up -d api demo
```

Then open <http://localhost:8501>.

Stop it with:

```bash
docker compose --profile demo down
```

## Configuration (env, set in `docker-compose.yml`)

| Var | Default | Meaning |
|---|---|---|
| `API_URL` | `http://api:8000/facepp/v3/compare` | Compare endpoint to call |
| `API_KEY` / `API_SECRET` | `attendance-key` / `attendance-secret` | Caller credentials |
| `SAMPLE_DIR` | `/app/samples` | Folder with sample faces (mounted from `./testdata`) |
| `SAMPLE_A` / `SAMPLE_B` | `face1.jpg` / `face2.jpg` | Sample file names |
| `VERIFY` | `1` | `0` skips TLS verification (set when pointing `API_URL` at nginx's self-signed HTTPS) |

To demo the full production path through nginx instead of hitting the API
directly, set `API_URL=https://nginx/facepp/v3/compare` and `VERIFY=0`.

## Note on scores

`confidence` and the FAR thresholds are **provisional placeholders** (Milestone 0
calibration pending), so treat the verdict as a structural demonstration, not a
final accuracy claim.
