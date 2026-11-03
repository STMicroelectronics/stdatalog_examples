"""
NotePulse – note_utils.py

High-precision musical pitch detection, frequency interpolation,
and note classification across the entire musical scale (C3 to C6).
"""

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Specialized ML target notes
MODEL_NOTES = ["C4", "C5", "F5"]

# Standard frequencies for reference
STANDARD_FREQUENCIES = {}
for midi in range(48, 85):
    name = NOTE_NAMES[midi % 12] + str(midi // 12 - 1)
    STANDARD_FREQUENCIES[name] = round(440.0 * (2.0 ** ((midi - 69) / 12.0)), 2)


def detect_pitch_and_confidence(audio: np.ndarray, fs: int = 44100) -> tuple:
    """
    Sub-Hertz high-precision fundamental pitch and harmonic confidence estimation.
    Uses Hann-windowed, zero-padded interpolated spectral peak analysis.

    Returns:
        (detected_freq_hz: float, confidence: float, rms: float)
    """
    if len(audio) == 0:
        return 0.0, 0.0, 0.0

    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 0.001:
        return 0.0, 0.0, rms

    # Remove DC offset
    audio_norm = audio - np.mean(audio)
    peak_amp = np.max(np.abs(audio_norm))
    if peak_amp > 0:
        audio_norm = audio_norm / peak_amp

    # Hann window + zero padding for high spectral interpolation
    w = np.hanning(len(audio_norm))
    n_fft = 16384
    fft = np.fft.rfft(audio_norm * w, n=n_fft)
    mag = np.abs(fft)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)

    # Restrict to musical pitch band (80 Hz to 1200 Hz)
    idx_start = max(1, int(np.ceil(80.0 / (fs / n_fft))))
    idx_end   = min(len(mag) - 2, int(np.floor(1200.0 / (fs / n_fft))))

    mag_band = mag[idx_start:idx_end]
    if len(mag_band) == 0:
        return 0.0, 0.0, rms

    peak_local = np.argmax(mag_band)
    peak_idx = idx_start + peak_local

    # Parabolic interpolation for sub-Hertz accuracy
    a = float(mag[peak_idx - 1])
    b = float(mag[peak_idx])
    c = float(mag[peak_idx + 1])
    denom = a - 2.0 * b + c
    if abs(denom) > 1e-12:
        delta = 0.5 * (a - c) / denom
    else:
        delta = 0.0

    detected_freq = (peak_idx + delta) * (fs / n_fft)

    # Harmonic-to-total energy ratio for pitch confidence
    peak_energy = b + a + c
    total_energy = np.sum(mag_band) + 1e-12
    energy_ratio = peak_energy / total_energy

    # Scale energy ratio to realistic confidence score (0.50 to 0.98 for clear tone)
    confidence = float(np.clip(energy_ratio * 4.5, 0.35, 0.98))

    return float(detected_freq), float(confidence), float(rms)


def frequency_to_note(freq: float) -> dict:
    """
    Convert a physical frequency (Hz) to its exact musical note,
    target frequency, MIDI number, and cents tuning deviation.
    """
    if freq < 65.0 or freq > 1500.0 or np.isnan(freq):
        return {
            "note": "—",
            "pitch_class": "—",
            "octave": 0,
            "midi": 0.0,
            "target_freq": 0.0,
            "cents_off": 0.0,
            "is_known_model": False,
            "tuning_status": "NONE"
        }

    # Standard formula: midi = 69 + 12 * log2(freq / 440)
    midi_float = 69.0 + 12.0 * np.log2(freq / 440.0)
    midi_round = int(round(midi_float))

    pitch_class = NOTE_NAMES[midi_round % 12]
    octave = (midi_round // 12) - 1
    note_name = f"{pitch_class}{octave}"

    target_freq = 440.0 * (2.0 ** ((midi_round - 69) / 12.0))
    cents_off = round(1200.0 * np.log2(freq / target_freq), 1)

    if abs(cents_off) <= 15:
        tuning_status = "IN_TUNE"
    elif cents_off > 15:
        tuning_status = "SHARP"
    else:
        tuning_status = "FLAT"

    return {
        "note": note_name,
        "pitch_class": pitch_class,
        "octave": octave,
        "midi": round(float(midi_float), 2),
        "target_freq": round(float(target_freq), 2),
        "cents_off": float(cents_off),
        "is_known_model": note_name in MODEL_NOTES,
        "tuning_status": tuning_status
    }
