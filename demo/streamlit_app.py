"""Stakeholder demo for the WiseFace face-compare API.

Upload (or pick sample) two face images, call the compare endpoint, and show the
confidence + match verdict in a clean, light-mode UI. Styling follows the DCT
web palette: brand #5ba1b5, success/danger/warning badge families, neutral text.
"""
from __future__ import annotations

import os

import requests
import streamlit as st

# --- Config (env-overridable so the same image runs against any backend) ---
API_URL = os.environ.get("API_URL", "http://api:8000/facepp/v3/compare")
API_KEY = os.environ.get("API_KEY", "attendance-key")
API_SECRET = os.environ.get("API_SECRET", "attendance-secret")
VERIFY_TLS = os.environ.get("VERIFY", "1") != "0"
SAMPLE_DIR = os.environ.get("SAMPLE_DIR", "/app/samples")
SAMPLE_A = os.environ.get("SAMPLE_A", "face1.jpg")
SAMPLE_B = os.environ.get("SAMPLE_B", "face2.jpg")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "60"))

st.set_page_config(
    page_title="WiseFace - Uji Banding Wajah",
    layout="centered",
)

# --- Palette-driven styling (DCT web). Light mode only. ---
st.markdown(
    """
    <style>
      .wf-header { background:#5ba1b5; color:#ffffff; padding:16px 22px;
                   border-radius:6px; margin-bottom:6px; }
      .wf-header h1 { margin:0; font-size:22px; font-weight:700; }
      .wf-header p  { margin:2px 0 0; font-size:13px; opacity:.92; }
      .wf-label { font-size:12px; font-weight:700; text-transform:uppercase;
                  letter-spacing:.05em; color:#6c757d; margin-bottom:2px; }
      .wf-value { font-size:15px; color:#212529; }
      .wf-conf  { font-size:52px; font-weight:700; color:#212529; line-height:1; }
      .wf-conf small { font-size:18px; color:#6c757d; font-weight:600; }
      .wf-badge { display:inline-block; padding:7px 16px; border-radius:4px;
                  font-weight:700; font-size:15px; letter-spacing:.02em; }
      .wf-badge.success { background:#d1eddc; border:1px solid #28a745; color:#155724; }
      .wf-badge.danger  { background:#f8d7da; border:1px solid #dc3545; color:#721c24; }
      .wf-badge.warning { background:#fff3cd; border:1px solid #ffc107; color:#856404; }
      .wf-note  { font-size:12px; color:#6c757d; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="wf-header">
      <h1>WiseFace - Uji Banding Wajah</h1>
      <p>Bandingkan dua foto wajah dan lihat skor kemiripan (confidence) dari layanan compare.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Helpers --------------------------------------------------------------- #
def fmt_decimal(value: float, places: int = 2) -> str:
    """Indonesian decimal format: 1.234,56 (period thousands, comma decimal)."""
    s = f"{value:,.{places}f}"
    return s.replace(",", "·").replace(".", ",").replace("·", ".")


def fmt_int(value: int) -> str:
    """Indonesian integer format: 1.322."""
    return f"{value:,}".replace(",", ".")


def load_sample(name: str) -> bytes | None:
    path = os.path.join(SAMPLE_DIR, name)
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def verdict(confidence: float, thresholds: dict) -> tuple[str, str, str]:
    """(label, detail, badge-class) from confidence vs the FAR threshold tiers.

    Face++ semantics: confidence >= a tier's threshold means "same person" at
    that false-accept rate. Stricter tier (1e-5) implies the looser ones.
    """
    t3 = thresholds.get("1e-3")
    t4 = thresholds.get("1e-4")
    t5 = thresholds.get("1e-5")
    if t5 is not None and confidence >= t5:
        return ("COCOK", f"Sangat kuat - lolos ambang FAR 1e-5 ({fmt_decimal(t5)})", "success")
    if t4 is not None and confidence >= t4:
        return ("COCOK", f"Kuat - lolos ambang FAR 1e-4 ({fmt_decimal(t4)})", "success")
    if t3 is not None and confidence >= t3:
        return ("COCOK", f"Lolos ambang FAR 1e-3 ({fmt_decimal(t3)})", "success")
    return ("TIDAK COCOK", "Di bawah semua ambang kecocokan", "danger")


def call_compare(img1: bytes, img2: bytes) -> tuple[dict | None, dict | None]:
    """POST both images. Returns (success_body, error_info)."""
    files = {
        "image_file1": ("image1.jpg", img1, "image/jpeg"),
        "image_file2": ("image2.jpg", img2, "image/jpeg"),
    }
    params = {"api_key": API_KEY, "api_secret": API_SECRET}
    try:
        resp = requests.post(
            API_URL, params=params, files=files,
            timeout=REQUEST_TIMEOUT, verify=VERIFY_TLS,
        )
    except requests.RequestException as exc:
        return None, {"kind": "connection", "detail": str(exc)}
    try:
        body = resp.json()
    except ValueError:
        return None, {"kind": "http", "status": resp.status_code, "detail": resp.text[:300]}
    if resp.status_code == 200:
        return body, None
    return None, {"kind": "api", "status": resp.status_code,
                  "message": body.get("error_message", "?"), "body": body}


# --- Sidebar: connection settings ------------------------------------------ #
with st.sidebar:
    st.markdown('<div class="wf-label">Koneksi Layanan</div>', unsafe_allow_html=True)
    api_url = st.text_input("Endpoint", value=API_URL)
    api_key = st.text_input("API Key", value=API_KEY)
    api_secret = st.text_input("API Secret", value=API_SECRET, type="password")
    API_URL, API_KEY, API_SECRET = api_url, api_key, api_secret
    st.divider()
    st.markdown(
        '<div class="wf-note">Catatan: nilai confidence dan ambang batas masih '
        'bersifat sementara (placeholder Milestone 0) dan belum dikalibrasi '
        'terhadap data FAR/FRR final.</div>',
        unsafe_allow_html=True,
    )

# --- Image source ---------------------------------------------------------- #
samples_present = (
    load_sample(SAMPLE_A) is not None and load_sample(SAMPLE_B) is not None
)
source_options = ["Unggah file"] + (["Gunakan contoh wajah"] if samples_present else [])
source = st.radio("Sumber gambar", source_options, horizontal=True)

img1_bytes: bytes | None = None
img2_bytes: bytes | None = None

if source == "Gunakan contoh wajah":
    img1_bytes = load_sample(SAMPLE_A)
    img2_bytes = load_sample(SAMPLE_B)
else:
    up_col1, up_col2 = st.columns(2)
    with up_col1:
        up1 = st.file_uploader("Gambar 1", type=["jpg", "jpeg", "png"], key="u1")
        if up1 is not None:
            img1_bytes = up1.getvalue()
    with up_col2:
        up2 = st.file_uploader("Gambar 2", type=["jpg", "jpeg", "png"], key="u2")
        if up2 is not None:
            img2_bytes = up2.getvalue()

# Previews
prev1, prev2 = st.columns(2)
with prev1:
    st.markdown('<div class="wf-label">Gambar 1</div>', unsafe_allow_html=True)
    if img1_bytes:
        st.image(img1_bytes, use_container_width=True)
    else:
        st.markdown('<div class="wf-note">Belum ada gambar.</div>', unsafe_allow_html=True)
with prev2:
    st.markdown('<div class="wf-label">Gambar 2</div>', unsafe_allow_html=True)
    if img2_bytes:
        st.image(img2_bytes, use_container_width=True)
    else:
        st.markdown('<div class="wf-note">Belum ada gambar.</div>', unsafe_allow_html=True)

st.divider()

ready = bool(img1_bytes and img2_bytes)
go = st.button("Bandingkan Wajah", type="primary", disabled=not ready, use_container_width=True)
if not ready:
    st.markdown(
        '<div class="wf-note">Sediakan dua gambar untuk mulai membandingkan.</div>',
        unsafe_allow_html=True,
    )

if go and ready:
    with st.spinner("Memproses perbandingan..."):
        body, err = call_compare(img1_bytes, img2_bytes)
    st.session_state["result"] = body
    st.session_state["error"] = err

# --- Render result --------------------------------------------------------- #
result = st.session_state.get("result")
error = st.session_state.get("error")

if error:
    if error["kind"] == "connection":
        st.markdown(
            f'<span class="wf-badge danger">GAGAL TERHUBUNG</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="wf-note">{error["detail"]}</div>', unsafe_allow_html=True)
    elif error["kind"] == "api":
        st.markdown(
            f'<span class="wf-badge danger">{error["message"]}</span>'
            f'&nbsp;&nbsp;<span class="wf-note">HTTP {error["status"]}</span>',
            unsafe_allow_html=True,
        )
        with st.expander("Respons mentah (JSON)"):
            st.json(error["body"])
    else:
        st.markdown(
            f'<span class="wf-badge danger">HTTP {error.get("status", "?")}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="wf-note">{error["detail"]}</div>', unsafe_allow_html=True)

elif result:
    confidence = float(result.get("confidence", 0.0))
    thresholds = result.get("thresholds", {})
    label, detail, badge = verdict(confidence, thresholds)

    st.markdown(f'<span class="wf-badge {badge}">{label}</span>', unsafe_allow_html=True)
    st.markdown(f'<div class="wf-note" style="margin-top:6px">{detail}</div>',
                unsafe_allow_html=True)

    st.write("")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown('<div class="wf-label">Confidence</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="wf-conf">{fmt_decimal(confidence)} <small>/ 100</small></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown('<div class="wf-label">Waktu Proses</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="wf-value">{fmt_int(int(result.get("time_used", 0)))} ms</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="wf-label" style="margin-top:10px">Request ID</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="wf-value">{result.get("request_id", "-")}</div>',
                    unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="wf-label">Ambang Kecocokan (FAR)</div>', unsafe_allow_html=True)
    rows = []
    for tier in ("1e-3", "1e-4", "1e-5"):
        if tier in thresholds:
            passed = confidence >= thresholds[tier]
            rows.append({
                "Tingkat FAR": tier,
                "Ambang": fmt_decimal(thresholds[tier]),
                "Status": "Lolos" if passed else "Tidak lolos",
            })
    if rows:
        st.table(rows)

    with st.expander("Respons mentah (JSON)"):
        st.json(result)
