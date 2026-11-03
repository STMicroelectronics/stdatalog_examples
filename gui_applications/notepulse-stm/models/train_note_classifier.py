import os
import wave
import warnings

import joblib
import numpy as np
import pandas as pd

from scipy.signal import stft
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.metrics import classification_report, confusion_matrix


# ============================================================
# CONFIGURATION
# ============================================================

AUDIO_DIR = r"C:\Users\Mahek\Downloads\audiofiles"

MODEL_OUTPUT = r"C:\Users\Mahek\stdatalog-pysdk\note_classifier.joblib"

WINDOW_SECONDS = 0.50
STEP_SECONDS = 0.25

# Frequency range relevant for the notes in this dataset.
MIN_FREQ = 80
MAX_FREQ = 1200

TARGET_FILES = [
    "f1_long_straight_a.wav",
    "f1_long_straight_e.wav",
    "f1_long_straight_i.wav",
    "f1_long_straight_o.wav",
    "f1_long_straight_u.wav",
]


# ============================================================
# KNOWN AUDIO ANNOTATIONS
# ============================================================
#
# These are NOT the classifier's predictions.
#
# They are the ground-truth boundaries of the five audio files
# available to us. Each region is then cut into many smaller
# training windows.
#
# The ML model does NOT receive the note name as an input feature.
# It only receives the audio-derived features.
#
# ============================================================

SEGMENTS = [

    # --------------------------------------------------------
    # f1_long_straight_a.wav
    # --------------------------------------------------------
    ("f1_long_straight_a.wav", 0.83592, 3.57588, "C4"),
    ("f1_long_straight_a.wav", 4.36535, 6.93116, "C5"),
    ("f1_long_straight_a.wav", 7.66259, 10.73923, "F5"),

    # --------------------------------------------------------
    # f1_long_straight_e.wav
    # --------------------------------------------------------
    ("f1_long_straight_e.wav", 0.87075, 3.13470, "C4"),
    ("f1_long_straight_e.wav", 3.77325, 6.31583, "C5"),
    ("f1_long_straight_e.wav", 6.84989, 9.42730, "F5"),

    # --------------------------------------------------------
    # f1_long_straight_i.wav
    # --------------------------------------------------------
    ("f1_long_straight_i.wav", 0.52245, 2.82123, "C4"),
    ("f1_long_straight_i.wav", 3.49461, 5.92109, "C5"),
    ("f1_long_straight_i.wav", 6.61769, 9.58984, "F5"),

    # --------------------------------------------------------
    # f1_long_straight_o.wav
    # --------------------------------------------------------
    ("f1_long_straight_o.wav", 0.98685, 3.32046, "C4"),
    ("f1_long_straight_o.wav", 4.08671, 6.42032, "C5"),
    ("f1_long_straight_o.wav", 7.03565, 9.84526, "F5"),

    # --------------------------------------------------------
    # f1_long_straight_u.wav
    # --------------------------------------------------------
    ("f1_long_straight_u.wav", 0.37152, 2.76318, "C4"),
    ("f1_long_straight_u.wav", 3.55266, 5.92109, "C5"),
    ("f1_long_straight_u.wav", 6.76862, 9.60145, "F5"),
]


# ============================================================
# AUDIO LOADING
# ============================================================

def load_wav(path):
    """
    Load a mono 16-bit WAV file.
    """

    with wave.open(path, "rb") as wav:

        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()

        frames = wav.readframes(wav.getnframes())

    if channels != 1:
        raise ValueError(
            f"{path} is not mono. Channels = {channels}"
        )

    if sample_width != 2:
        raise ValueError(
            f"{path} is not 16-bit PCM. Sample width = {sample_width}"
        )

    audio = np.frombuffer(
        frames,
        dtype=np.int16
    ).astype(np.float32)

    # Normalize amplitude.
    audio /= 32768.0

    # Remove DC offset.
    audio -= np.mean(audio)

    return audio, sample_rate


# ============================================================
# FEATURE EXTRACTION
# ============================================================

def frequency_to_midi(freq):
    """
    Convert frequency to MIDI number.
    """

    if freq <= 0:
        return 0.0

    return 69.0 + 12.0 * np.log2(freq / 440.0)


def extract_features(audio, sample_rate):
    """
    Extract pitch-oriented and spectral features.

    The model never receives the note label here.

    Features include:
        - log-frequency spectral representation
        - spectral centroid
        - spectral spread
        - spectral rolloff
        - spectral flatness
        - dominant frequency
        - pitch estimate
        - MIDI estimate
        - harmonic strength
        - chroma-like pitch-class representation
    """

    audio = audio.astype(np.float32)

    # Remove DC.
    audio -= np.mean(audio)

    # Normalize.
    max_amp = np.max(np.abs(audio))

    if max_amp > 0:
        audio = audio / max_amp

    # --------------------------------------------------------
    # STFT
    # --------------------------------------------------------

    n_fft = 4096

    frequencies, _, Z = stft(
        audio,
        fs=sample_rate,
        window="hann",
        nperseg=n_fft,
        noverlap=n_fft // 2,
        boundary=None
    )

    magnitude = np.abs(Z)

    # Average over time.
    spectrum = np.mean(magnitude, axis=1)

    # Frequency range.
    mask = (
        (frequencies >= MIN_FREQ) &
        (frequencies <= MAX_FREQ)
    )

    freqs = frequencies[mask]
    spectrum = spectrum[mask]

    if len(freqs) == 0:
        return np.zeros(1, dtype=np.float32)

    # --------------------------------------------------------
    # Normalize spectral shape
    # --------------------------------------------------------

    total_energy = np.sum(spectrum)

    if total_energy > 0:
        normalized_spectrum = spectrum / total_energy
    else:
        normalized_spectrum = spectrum

    # --------------------------------------------------------
    # Spectral centroid
    # --------------------------------------------------------

    centroid = np.sum(
        freqs * normalized_spectrum
    )

    # --------------------------------------------------------
    # Spectral spread
    # --------------------------------------------------------

    spread = np.sqrt(
        np.sum(
            ((freqs - centroid) ** 2)
            * normalized_spectrum
        )
    )

    # --------------------------------------------------------
    # Spectral rolloff
    # --------------------------------------------------------

    cumulative = np.cumsum(normalized_spectrum)

    rolloff_index = np.searchsorted(
        cumulative,
        0.85
    )

    rolloff_index = min(
        rolloff_index,
        len(freqs) - 1
    )

    rolloff = freqs[rolloff_index]

    # --------------------------------------------------------
    # Spectral flatness
    # --------------------------------------------------------

    geometric_mean = np.exp(
        np.mean(
            np.log(
                spectrum + 1e-12
            )
        )
    )

    arithmetic_mean = np.mean(
        spectrum + 1e-12
    )

    flatness = geometric_mean / arithmetic_mean

    # --------------------------------------------------------
    # Dominant spectral peak
    # --------------------------------------------------------

    peak_index = np.argmax(spectrum)

    dominant_frequency = freqs[peak_index]

    # --------------------------------------------------------
    # Pitch estimation
    # --------------------------------------------------------
    #
    # Instead of blindly using the largest FFT peak,
    # inspect possible fundamentals and their harmonics.
    #
    # This helps prevent:
    #
    # A4 fundamental = 440 Hz
    # second harmonic = 880 Hz
    #
    # from being classified as A5.
    # --------------------------------------------------------

    candidate_frequencies = np.linspace(
        MIN_FREQ,
        MAX_FREQ / 2,
        1000
    )

    scores = []

    for fundamental in candidate_frequencies:

        score = 0.0

        # Check first several harmonics.
        for harmonic in range(1, 6):

            target = fundamental * harmonic

            if target > MAX_FREQ:
                break

            index = np.argmin(
                np.abs(freqs - target)
            )

            # Give stronger weight to the fundamental.
            weight = 1.0 / harmonic

            score += (
                normalized_spectrum[index]
                * weight
            )

        scores.append(score)

    pitch_index = np.argmax(scores)

    estimated_frequency = candidate_frequencies[pitch_index]

    estimated_midi = frequency_to_midi(
        estimated_frequency
    )

    # --------------------------------------------------------
    # Harmonic ratios
    # --------------------------------------------------------

    harmonic_features = []

    fundamental = estimated_frequency

    fundamental_index = np.argmin(
        np.abs(freqs - fundamental)
    )

    fundamental_energy = (
        spectrum[fundamental_index] + 1e-12
    )

    for harmonic in range(1, 6):

        target = fundamental * harmonic

        if target > MAX_FREQ:
            harmonic_features.append(0.0)
            continue

        index = np.argmin(
            np.abs(freqs - target)
        )

        ratio = (
            spectrum[index] /
            fundamental_energy
        )

        harmonic_features.append(
            ratio
        )

    # --------------------------------------------------------
    # Chroma / pitch-class features
    # --------------------------------------------------------
    #
    # This makes the representation more related to musical
    # pitch than absolute FFT bins.
    # --------------------------------------------------------

    chroma = np.zeros(12)

    for freq, magnitude_value in zip(
        freqs,
        spectrum
    ):

        if freq <= 0:
            continue

        midi = frequency_to_midi(freq)

        pitch_class = int(
            round(midi)
        ) % 12

        chroma[pitch_class] += magnitude_value

    chroma_sum = np.sum(chroma)

    if chroma_sum > 0:
        chroma /= chroma_sum

    # --------------------------------------------------------
    # Final feature vector
    # --------------------------------------------------------

    features = np.concatenate([
        # Spectral shape
        normalized_spectrum,

        # Scalar spectral features
        [
            centroid,
            spread,
            rolloff,
            flatness,

            dominant_frequency,

            estimated_frequency,
            estimated_midi,
        ],

        # Harmonics
        harmonic_features,

        # Pitch classes
        chroma
    ])

    return features.astype(np.float32)


# ============================================================
# CREATE TRAINING WINDOWS
# ============================================================

def create_dataset():
    """
    Convert annotated note regions into many short
    overlapping training examples.
    """

    X = []
    y = []
    groups = []

    print("\nCreating training samples...\n")

    loaded_files = {}

    for filename, start_time, end_time, note in SEGMENTS:

        path = os.path.join(
            AUDIO_DIR,
            filename
        )

        if not os.path.exists(path):

            print(
                "WARNING: Missing file:",
                path
            )

            continue

        # Load each WAV only once.
        if filename not in loaded_files:

            print(
                "Loading:",
                filename
            )

            audio, sample_rate = load_wav(path)

            loaded_files[filename] = (
                audio,
                sample_rate
            )

        else:

            audio, sample_rate = loaded_files[
                filename
            ]

        start_sample = int(
            start_time * sample_rate
        )

        end_sample = int(
            end_time * sample_rate
        )

        segment = audio[
            start_sample:end_sample
        ]

        window_size = int(
            WINDOW_SECONDS * sample_rate
        )

        step_size = int(
            STEP_SECONDS * sample_rate
        )

        count = 0

        for start in range(
            0,
            len(segment) - window_size + 1,
            step_size
        ):

            window = segment[
                start:start + window_size
            ]

            # Skip extremely quiet windows.
            rms = np.sqrt(
                np.mean(window ** 2)
            )

            if rms < 0.005:
                continue

            features = extract_features(
                window,
                sample_rate
            )

            X.append(features)
            y.append(note)

            # IMPORTANT:
            # Group by recording, not individual window.
            #
            # This prevents nearly identical neighboring
            # windows from leaking between train and test.
            groups.append(filename)

            count += 1

        print(
            f"  {filename:30s} "
            f"{note:3s} -> {count} windows"
        )

    return (
        np.asarray(X),
        np.asarray(y),
        np.asarray(groups)
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    warnings.filterwarnings(
        "ignore"
    )

    print("=" * 60)
    print("MUSICAL NOTE CLASSIFIER TRAINING")
    print("=" * 60)

    print("\nAudio directory:")
    print(AUDIO_DIR)

    print("\nChecking audio files...")

    for filename in TARGET_FILES:

        path = os.path.join(
            AUDIO_DIR,
            filename
        )

        if os.path.exists(path):
            print("  OK:", filename)
        else:
            print("  MISSING:", filename)

    # --------------------------------------------------------
    # Create dataset
    # --------------------------------------------------------

    X, y, groups = create_dataset()

    print("\n")
    print("=" * 60)
    print("DATASET")
    print("=" * 60)

    print("Samples:", len(X))

    if len(X) == 0:
        raise RuntimeError(
            "No training samples were created."
        )

    print(
        "Features per sample:",
        X.shape[1]
    )

    print(
        "Classes:",
        sorted(np.unique(y))
    )

    print("\nSamples per class:")

    unique, counts = np.unique(
        y,
        return_counts=True
    )

    for label, count in zip(
        unique,
        counts
    ):

        print(
            f"  {label}: {count}"
        )

    print("\nGroups:")
    for group in np.unique(groups):
        print(" ", group)

    # --------------------------------------------------------
    # Machine learning pipeline
    # --------------------------------------------------------
    #
    # Scaling + SVM.
    #
    # Probability=True allows the realtime monitor to display
    # confidence values later.
    # --------------------------------------------------------

    model = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),

        (
            "classifier",
            SVC(
                kernel="rbf",
                C=10.0,
                gamma="scale",
                probability=True,
                class_weight="balanced",
                random_state=42
            )
        )
    ])

    # --------------------------------------------------------
    # Leave-One-Recording-Out validation
    # --------------------------------------------------------
    #
    # We deliberately DO NOT randomly split individual windows.
    #
    # If windows from the same recording appeared in both
    # train and test, accuracy would be misleadingly high.
    #
    # Instead:
    #
    #   train = 4 vowel recordings
    #   test  = 1 completely unseen vowel recording
    #
    # repeated for every recording.
    # --------------------------------------------------------

    print("\n")
    print("=" * 60)
    print("LEAVE-ONE-RECORDING-OUT VALIDATION")
    print("=" * 60)

    logo = LeaveOneGroupOut()

    predictions = cross_val_predict(
        model,
        X,
        y,
        groups=groups,
        cv=logo
    )

    print("\nClassification report:\n")

    print(
        classification_report(
            y,
            predictions,
            zero_division=0
        )
    )

    print("Confusion matrix:")

    labels = sorted(
        np.unique(y)
    )

    cm = confusion_matrix(
        y,
        predictions,
        labels=labels
    )

    print("\nLabels:", labels)
    print(cm)

    validation_accuracy = np.mean(
        predictions == y
    )

    print(
        "\nValidation accuracy:",
        f"{validation_accuracy * 100:.2f}%"
    )

    # --------------------------------------------------------
    # Train final model on ALL available audio
    # --------------------------------------------------------

    print("\n")
    print("=" * 60)
    print("TRAINING FINAL MODEL")
    print("=" * 60)

    model.fit(
        X,
        y
    )

    # --------------------------------------------------------
    # Save model
    # --------------------------------------------------------

    model_package = {
        "model": model,

        "sample_rate": 44100,

        "window_seconds": WINDOW_SECONDS,

        "step_seconds": STEP_SECONDS,

        "min_frequency": MIN_FREQ,

        "max_frequency": MAX_FREQ,

        "classes": sorted(
            np.unique(y)
        ),

        "feature_count": X.shape[1],

        "training_files": TARGET_FILES,

        "validation_accuracy": float(
            validation_accuracy
        )
    }

    joblib.dump(
        model_package,
        MODEL_OUTPUT
    )

    print("\n")
    print("=" * 60)
    print("MODEL SAVED")
    print("=" * 60)

    print(
        MODEL_OUTPUT
    )

    print("\nTraining complete.")