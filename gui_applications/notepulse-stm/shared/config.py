"""
NotePulse – Shared configuration.

All backend modules and the server import from here.
Changing values here propagates everywhere.
"""

import os

# ──────────────────────────────────────────────
# ST SDK & Paths
# ──────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(REPO_ROOT, "models")

# Default SDK path (can also be customized via ST_SDK_ROOT environment variable)
SDK_ROOT = os.environ.get("ST_SDK_ROOT", r"C:\Users\Mahek\stdatalog-pysdk")

# ──────────────────────────────────────────────
# ML Model
# ──────────────────────────────────────────────
# Check local models/ folder first, fall back to SDK root if needed
LOCAL_MODEL_PATH = os.path.join(MODELS_DIR, "note_classifier.joblib")
SDK_MODEL_PATH   = os.path.join(SDK_ROOT, "note_classifier.joblib")
MODEL_PATH       = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else SDK_MODEL_PATH

KNOWN_NOTES = ["C4", "C5", "F5"]

# Confidence below this threshold → show LOW_CONFIDENCE instead of a note
CONFIDENCE_THRESHOLD = 0.55

# ──────────────────────────────────────────────
# Audio & SensorTile
# ──────────────────────────────────────────────
SENSOR_NAME = "mp23db01hp_mic"

# SensorTile delivers audio at 48 kHz
SENSOR_SAMPLE_RATE = 48_000

# Model was trained at 44.1 kHz → resample before feature extraction
MODEL_SAMPLE_RATE = 44_100

# Analysis window and hop (in seconds)
WINDOW_SECONDS = 0.50
STEP_SECONDS   = 0.25

# Samples in one analysis window (at SENSOR_SAMPLE_RATE)
WINDOW_SAMPLES = int(WINDOW_SECONDS * SENSOR_SAMPLE_RATE)   # 24 000
STEP_SAMPLES   = int(STEP_SECONDS   * SENSOR_SAMPLE_RATE)   # 12 000

# Minimum RMS to bother classifying (SensorTile quiet room is ~0.0001, voice is ~0.0008-0.002)
MIN_RMS = 0.00025

# ──────────────────────────────────────────────
# WebSocket server
# ──────────────────────────────────────────────
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8765

# ──────────────────────────────────────────────
# HSDLink
# ──────────────────────────────────────────────
ACQUISITION_FOLDER = os.path.join(SDK_ROOT, "_notepulse_tmp")
HSD_COM_TYPE = "st_hsd"
DEVICE_ID = 0
