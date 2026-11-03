"""
NotePulse – audio_processor.py

Continuously reads 0.5-second rolling windows from the RollingAudioBuffer,
resamples from 48 kHz → 44.1 kHz, runs the exact feature extraction
pipeline used during training, and emits rich musical pitch predictions
and contour telemetry every 0.25 seconds.
"""

import os
import sys
import time
import logging
import threading
from typing import Optional, Callable

import numpy as np

# ── SDK / config paths ─────────────────────────────────────────────────────
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)
import config

SDK_ROOT = config.SDK_ROOT
if SDK_ROOT not in sys.path:
    sys.path.insert(0, SDK_ROOT)

log = logging.getLogger("notepulse.processor")


# ── Reuse the exact feature extractor from training ────────────────────────
def _load_extract_features():
    """
    Import extract_features() from models/ or the original training script.
    Guarantees zero feature extraction drift from training time.
    """
    import importlib.util
    models_script = os.path.join(os.path.dirname(__file__), "..", "models", "train_note_classifier.py")
    sdk_script = os.path.join(SDK_ROOT, "train_note_classifier.py")
    train_script = models_script if os.path.exists(models_script) else sdk_script
    spec = importlib.util.spec_from_file_location("train_note_classifier", train_script)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.extract_features

_extract_features: Optional[Callable] = None

def get_extract_features() -> Callable:
    global _extract_features
    if _extract_features is None:
        _extract_features = _load_extract_features()
    return _extract_features


# ══════════════════════════════════════════════════════════════════════════════
# Audio processor
# ══════════════════════════════════════════════════════════════════════════════

class AudioProcessor:
    """
    Runs in a dedicated worker thread.
    Every STEP_SECONDS (~250 ms), analyzes a 0.5s audio window:
      1. Computes RMS signal level
      2. If silent (RMS < MIN_RMS), sends SILENCE
      3. Otherwise resamples 48 kHz → 44.1 kHz
      4. Extracts 128 features (STFT + pitch + chroma + harmonics)
      5. Runs ModelService (both physical pitch analysis and 3-note SVM)
      6. Emits prediction with latency telemetry
    """

    def __init__(
        self,
        audio_buffer,
        model_service,
        on_prediction: Callable,
        mock_mode: bool = False,
        input_sr: int = config.SENSOR_SAMPLE_RATE,
    ):
        self.audio_buffer   = audio_buffer
        self.model_service  = model_service
        self.on_prediction  = on_prediction
        self.mock_mode      = mock_mode
        self.input_sr       = input_sr
        self.window_samples = int(config.WINDOW_SECONDS * input_sr)
        self._stop_event    = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="AudioProcessorThread", daemon=True
        )
        self._thread.start()
        log.info("AudioProcessor: started (mock_mode=%s).", self.mock_mode)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        log.info("AudioProcessor: stopped.")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── main processing loop ──────────────────────────────────────────────

    def _loop(self) -> None:
        if self.mock_mode:
            self._mock_loop()
            return

        extract_features = get_extract_features()
        step = config.STEP_SECONDS

        while not self._stop_event.is_set():
            t0 = time.time()
            try:
                self._process_one_window(extract_features)
            except Exception as exc:
                log.error("AudioProcessor error: %s", exc, exc_info=True)
                self.on_prediction({"status": "ERROR", "error": str(exc)})

            elapsed = time.time() - t0
            wait = max(0.0, step - elapsed)
            self._stop_event.wait(timeout=wait)

    def _process_one_window(self, extract_features: Callable) -> None:
        t_start = time.time()

        window = self.audio_buffer.get_window(self.window_samples)
        if window is None:
            return

        # ── signal level (RMS) ────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(window ** 2)))
        signal_level = round(min(rms / 0.006, 1.0), 3)

        if rms < config.MIN_RMS:
            self.on_prediction({
                "timestamp":     time.time(),
                "note":          "—",
                "musical_note":  "—",
                "frequency":     0.0,
                "target_freq":   0.0,
                "cents_off":     0.0,
                "tuning_status": "NONE",
                "midi":          0.0,
                "confidence":    0.0,
                "ml_confidence": 0.0,
                "pitch_clarity": 0.0,
                "signal_level":  signal_level,
                "status":        "SILENCE",
                "latency_ms":    0.0,
                "waveform":      _downsample_waveform(window),
                "is_model_note": False,
            })
            return

        # ── resample if needed (e.g. 48 kHz → 44.1 kHz) ──────────────────
        if self.input_sr == config.MODEL_SAMPLE_RATE:
            resampled = window.astype(np.float32)
        else:
            from scipy.signal import resample_poly
            resampled = resample_poly(window, up=147, down=160).astype(np.float32)

        # ── dynamic digital AGC for low-amplitude MEMS mic audio ─────────
        peak = float(np.max(np.abs(resampled)))
        if peak > 0.0003:
            gain = min(0.5 / peak, 60.0)
            resampled_norm = (resampled * gain).astype(np.float32)
        else:
            resampled_norm = resampled

        # ── feature extraction (128 features) ────────────────────────────
        features = extract_features(resampled_norm, config.MODEL_SAMPLE_RATE)
        if features is None or len(features) == 0:
            return

        # ── note and pitch prediction ─────────────────────────────────────
        result = self.model_service.predict(features, audio=resampled_norm)

        # Backend computation time in milliseconds
        latency_ms = round((time.time() - t_start) * 1000, 1)

        result.update({
            "timestamp":    time.time(),
            "signal_level": signal_level,
            "latency_ms":   latency_ms,
            "waveform":     _downsample_waveform(window),
        })
        self.on_prediction(result)

    # ── mock simulation mode ──────────────────────────────────────────────

    def _mock_loop(self) -> None:
        """Simulates realistic singing and pitch transitions."""
        import math, random
        from note_utils import frequency_to_note

        scale = [
            ("C4", 261.63),
            ("D4", 293.66),
            ("E4", 329.63),
            ("F4", 349.23),
            ("G4", 392.00),
            ("A4", 440.00),
            ("B4", 493.88),
            ("C5", 523.25),
            ("F5", 698.46)
        ]

        step = config.STEP_SECONDS
        t = 0.0

        while not self._stop_event.is_set():
            t_start = time.time()
            idx = int(t / 2.0) % len(scale)
            note_name, base_freq = scale[idx]

            # Add vocal vibrato (~5 Hz modulation)
            vibrato = 3.0 * math.sin(2 * math.pi * 5.0 * t)
            freq = base_freq + vibrato
            note_info = frequency_to_note(freq)

            is_model = note_info["is_known_model"]
            status = "LIVE" if is_model else "OUTSIDE_RANGE"
            conf = 0.88 + 0.08 * math.sin(t)

            wave = [round(0.4 * math.sin(2 * math.pi * freq * i / 48000.0 + t), 3)
                    for i in range(200)]

            latency_ms = round(random.uniform(28.0, 42.0), 1)

            self.on_prediction({
                "timestamp":     time.time(),
                "note":          note_info["note"],
                "musical_note":  note_info["note"],
                "frequency":     round(freq, 2),
                "target_freq":   note_info["target_freq"],
                "cents_off":     note_info["cents_off"],
                "tuning_status": note_info["tuning_status"],
                "midi":          note_info["midi"],
                "confidence":    round(conf, 3),
                "ml_confidence": round(0.85 if is_model else 0.40, 3),
                "pitch_clarity": round(conf, 3),
                "signal_level":  round(0.65 + 0.15 * math.sin(t * 1.5), 3),
                "status":        status,
                "latency_ms":    latency_ms,
                "waveform":      wave,
                "is_model_note": is_model,
                "all_probs": {
                    "C4": round(0.85 if note_name == "C4" else 0.08, 3),
                    "C5": round(0.88 if note_name == "C5" else 0.06, 3),
                    "F5": round(0.92 if note_name == "F5" else 0.05, 3),
                }
            })

            t += step
            self._stop_event.wait(timeout=step)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _downsample_waveform(audio: np.ndarray, target: int = 200) -> list:
    """Downsample audio to 200 points with dynamic visual gain."""
    if len(audio) == 0:
        return []
    peak = float(np.max(np.abs(audio)))
    gain = min(0.7 / peak, 40.0) if peak > 0.0003 else 1.0
    step = max(1, len(audio) // target)
    return [round(float(audio[i] * gain), 3) for i in range(0, len(audio), step)][:target]
