"""Burst-test summary report — embedded HTML stakeholder page."""
from __future__ import annotations

import os
import pathlib

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="WiseFace - Laporan Burst Test",
    layout="wide",
)

# Resolve the report HTML — mounted at /app/report in the container
# (see docker-compose.yml), falls back to the repo docs/ for local runs.
_CANDIDATES = [
    pathlib.Path("/app/report/burst-test-summary.html"),
    pathlib.Path(__file__).parent.parent.parent / "docs" / "burst-test-summary.html",
]

html_path: pathlib.Path | None = next(
    (p for p in _CANDIDATES if p.exists()), None
)

if html_path is None:
    st.error(
        "Laporan tidak ditemukan. "
        "Pastikan volume docs/ ter-mount di /app/report dalam container."
    )
    st.stop()

html_content = html_path.read_text(encoding="utf-8")

components.html(html_content, height=2600, scrolling=True)
