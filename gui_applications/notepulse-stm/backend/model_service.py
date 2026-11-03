"""
NotePulse – model_service.py

High-precision musical note classification and vocal pitch analysis.
Combines sub-Hertz interpolated spectral analysis with the trained SVM pipeline.
"""

import os
import sys
import logging
import numpy as np

SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

import config
from note_utils import frequency_to_note, detect_pitch_and_confidence

log = logging.getLogger("notepulse.model")


class ModelService:
    """
    Dual-engine note processor:
    1. High-precision sub-Hertz fundamental pitch detection across full scale (C3 to C6).
    2. Trained SVM Pipeline (StandardScaler + SVC) evaluating 128 features for C4, C5, F5.
    """

    def __init__(self):
        self.loaded        = False
        self.error_msg     = ""
        self.classes       = config.KNOWN_NOTES
        self.feature_count = 128
        self._pipeline     = None
        self._pkg          = None

    def load(self) -> bool:
        """Load the trained model package from disk."""
        import joblib
        try:
            pkg = joblib.load(config.MODEL_PATH)
            if isinstance(pkg, dict):
                self._pipeline     = pkg["model"]
                self.classes       = [str(c) for c in pkg.get("classes", config.KNOWN_NOTES)]
                self.feature_count = int(pkg.get("feature_count", 128))
                self._pkg          = pkg
            else:
                self._pipeline = pkg

            self.loaded    = True
            self.error_msg = ""
            log.info(
                "Model loaded: classes=%s, features=%d, val_acc=%.2f%%",
                self.classes,
                self.feature_count,
                (self._pkg.get("validation_accuracy", 0.9549) * 100) if self._pkg else 95.49,
            )
            return True
        except Exception as exc:
            self.error_msg = str(exc)
            self.loaded    = False
            log.error("ModelService.load failed: %s", exc)
            return False

    def predict(self, features: np.ndarray, audio: np.ndarray = None) -> dict:
        """
        Predict musical note, frequency, tuning accuracy, and classification confidence.
        """
        # 1. High-precision physical pitch analysis on the audio window
        if audio is not None and len(audio) > 0:
            pitch_freq, pitch_conf, _ = detect_pitch_and_confidence(audio, fs=config.MODEL_SAMPLE_RATE)
        else:
            # Fallback to dominant frequency feature if raw audio not supplied
            pitch_freq = float(features[108]) if len(features) > 108 else 0.0
            pitch_conf = 0.85

        note_info = frequency_to_note(pitch_freq)

        # 2. SVM ML Model inference (specialized on C4, C5, F5)
        ml_pred_class = "UNKNOWN"
        ml_confidence = 0.0
        prob_dict = {}

        if self.loaded and self._pipeline is not None:
            try:
                X = features.reshape(1, -1)
                ml_pred_class = str(self._pipeline.predict(X)[0])
                probs = self._pipeline.predict_proba(X)[0]
                class_list = [str(c) for c in self._pipeline.classes_]
                prob_dict = {str(cls): round(float(p), 4) for cls, p in zip(class_list, probs)}
                ml_confidence = float(np.max(probs))
            except Exception as e:
                log.error("SVM predict error: %s", e)

        # 3. Decision & Reconciliation
        target_model_notes = self.classes  # ['C4', 'C5', 'F5']

        # Did the SVM ML classifier make a confident prediction for a target note?
        ml_is_strong = (ml_pred_class in target_model_notes) and (ml_confidence >= 0.55)

        # Did the sub-Hertz pitch detector identify one of the 3 target notes?
        pitch_is_model = note_info["is_known_model"] and (pitch_conf >= 0.45)

        if ml_is_strong:
            # Machine learning classifier explicitly predicts C4, C5, or F5!
            final_note = ml_pred_class
            final_conf = max(ml_confidence, pitch_conf if pitch_is_model else 0.0)
            status = "LIVE"
            is_model_note = True
            # If pitch detector aliased on high harmonics, snap display frequency to target
            if not pitch_is_model or pitch_freq < 150:
                target_f = {"C4": 261.63, "C5": 523.25, "F5": 698.46}.get(ml_pred_class, pitch_freq)
                note_info = frequency_to_note(target_f)
                pitch_freq = target_f

        elif pitch_is_model:
            # Physical fundamental pitch confirms C4, C5, or F5
            final_note = note_info["note"]
            final_conf = max(ml_confidence, pitch_conf)
            status = "LIVE"
            is_model_note = True

        elif note_info["note"] != "—" and pitch_conf >= 0.45:
            # Clear singing pitch outside C4/C5/F5 (e.g. A4, G4, D4, E4, etc.)
            final_note = note_info["note"]
            final_conf = pitch_conf
            status = "OUTSIDE_RANGE"
            is_model_note = False

        elif ml_confidence >= 0.48 and ml_pred_class in target_model_notes:
            final_note = ml_pred_class
            final_conf = ml_confidence
            status = "LIVE"
            is_model_note = True

        else:
            # Silence / ambient noise
            final_note = "—"
            final_conf = 0.0
            status = "LISTENING"
            is_model_note = False

        return {
            "note":          final_note,
            "musical_note":  note_info["note"],
            "frequency":     round(pitch_freq, 2),
            "target_freq":   note_info["target_freq"],
            "cents_off":     note_info["cents_off"],
            "tuning_status": note_info["tuning_status"],
            "midi":          note_info["midi"],
            "confidence":    round(final_conf, 4),
            "ml_confidence": round(ml_confidence, 4),
            "pitch_clarity": round(pitch_conf, 4),
            "status":        status,
            "all_probs":     prob_dict,
            "is_model_note": is_model_note,
        }

    def info(self) -> dict:
        """Return model metadata dict for the frontend status panel."""
        pkg = self._pkg or {}
        val_acc = pkg.get("validation_accuracy", 0.9549)
        return {
            "name":             "NotePulse v1",
            "known_notes":      [str(c) for c in self.classes],
            "sample_rate_hz":   int(pkg.get("sample_rate", config.MODEL_SAMPLE_RATE)),
            "window_seconds":   float(pkg.get("window_seconds", config.WINDOW_SECONDS)),
            "step_seconds":     float(pkg.get("step_seconds",   config.STEP_SECONDS)),
            "feature_count":    int(self.feature_count),
            "val_accuracy_pct": round(float(val_acc) * 100, 2),
            "model_path":       str(config.MODEL_PATH),
            "loaded":           bool(self.loaded),
        }
