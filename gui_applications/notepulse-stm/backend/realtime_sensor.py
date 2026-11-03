"""
NotePulse – realtime_sensor.py

Connects to the SensorTile.box PRO via the official ST stdatalog-pysdk
(HSDLink / PnPL / USB) and feeds decoded audio into a thread-safe
RollingAudioBuffer using the SDK's official DataReader.

Key SDK Integration:
--------------------
1. HSDLink DLL singleton: libhs_datalog_v2 is loaded once per process.
2. DataReader: The official ST DataReader strips the 8-byte timestamps
   embedded every samples_per_ts (1000) samples and scales int16 PCM
   by sensitivity (1/32768) into clean float32 audio [-1, 1].
"""

import os
import sys
import struct
import logging
import threading
from collections import deque
from threading import Event, Thread
from typing import Optional

import numpy as np

# ── Paths & Virtualenv auto-injection ──────────────────────────────────────
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

import config

SDK_ROOT = config.SDK_ROOT
VENV_SITE_PACKAGES = os.path.join(SDK_ROOT, ".venv", "Lib", "site-packages")
EXTRA_PATHS = [
    SDK_ROOT,
    VENV_SITE_PACKAGES,
    os.path.join(SDK_ROOT, "stdatalog_core"),
    os.path.join(SDK_ROOT, "stdatalog_pnpl"),
    os.path.join(SDK_ROOT, "stdatalog_gui"),
    os.path.join(SDK_ROOT, "stdatalog_dtk"),
]
for p in EXTRA_PATHS:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from stdatalog_core.HSD_utils.DataReader import DataReader
from stdatalog_core.HSD_utils.DataClass import DataClass
from stdatalog_core.HSD.utils.type_conversion import TypeConversion

log = logging.getLogger("notepulse.sensor")


# ══════════════════════════════════════════════════════════════════════════════
# Module-level HSDLink singletons
# ══════════════════════════════════════════════════════════════════════════════

_hsd_link_singleton = None   # HSDLink manager (factory wrapper)
_hsd_singleton      = None   # HSDLink_v2 instance (actual link)


def _get_hsd_connection(acq_folder: str):
    """
    Return (hsd_link, hsd), creating them on first call only.
    Subsequent calls reuse the open DLL connection.
    """
    global _hsd_link_singleton, _hsd_singleton

    if _hsd_link_singleton is not None and _hsd_singleton is not None:
        log.info("Reusing existing HSDLink connection (DLL already open).")
        return _hsd_link_singleton, _hsd_singleton

    from stdatalog_core.HSD_link.HSDLink import HSDLink
    log.info("Opening HSDLink DLL (libhs_datalog_v2) ...")
    hsd_link = HSDLink()
    hsd = hsd_link.create_hsd_link(
        dev_com_type=config.HSD_COM_TYPE,
        acquisition_folder=acq_folder,
    )
    if hsd is None:
        raise RuntimeError(
            "HSDLink.create_hsd_link returned None — "
            "is the SensorTile connected and ST DATALOG GUI closed?"
        )

    _hsd_link_singleton = hsd_link
    _hsd_singleton      = hsd
    log.info("HSDLink DLL opened successfully.")
    return hsd_link, hsd


# ══════════════════════════════════════════════════════════════════════════════
# Rolling audio buffer
# ══════════════════════════════════════════════════════════════════════════════

class RollingAudioBuffer:
    """Thread-safe circular buffer for float32 audio samples."""

    def __init__(self, max_samples: int):
        self._buf  = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def push(self, samples: np.ndarray) -> None:
        with self._lock:
            self._buf.extend(samples.tolist())

    def get_window(self, n_samples: int) -> Optional[np.ndarray]:
        with self._lock:
            if len(self._buf) < n_samples:
                return None
            return np.array(list(self._buf)[-n_samples:], dtype=np.float32)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


# ══════════════════════════════════════════════════════════════════════════════
# Sensor session
# ══════════════════════════════════════════════════════════════════════════════

class SensorSession:
    """
    Manages start/stop of the microphone streaming session.
    """

    def __init__(self, audio_buffer: RollingAudioBuffer):
        self.audio_buffer  = audio_buffer
        self.connected     = False
        self.error_msg     = ""
        self._stop_event   = Event()
        self._stream_thread: Optional[Thread] = None
        self._hsd_link     = None
        self._hsd          = None
        self._acq_folder   = config.ACQUISITION_FOLDER
        os.makedirs(self._acq_folder, exist_ok=True)

    # ── public API ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Start (or restart) streaming.
        Safe to call multiple times — reuses the existing DLL connection.
        """
        try:
            self._connect()
            comp_status = self._enable_microphone()
            self._start_streaming(comp_status)
            self.connected = True
            self.error_msg = ""
            log.info("SensorSession: streaming started ✔")
            return True
        except Exception as exc:
            self.error_msg = str(exc)
            self.connected = False
            log.error("SensorSession.start failed: %s", exc)
            try:
                if self._hsd and self._hsd_link:
                    self._hsd_link.stop_log(self._hsd, config.DEVICE_ID)
            except Exception:
                pass
            return False

    def stop(self) -> None:
        """
        Stop the streaming thread and FW log.
        Keeps the HSDLink DLL connection alive for the next start() call.
        """
        self._stop_event.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=3)
        self._stream_thread = None

        try:
            if self._hsd and self._hsd_link:
                self._hsd_link.stop_log(self._hsd, config.DEVICE_ID)
        except Exception as exc:
            log.warning("stop_log failed: %s", exc)

        self.connected = False
        self.audio_buffer.clear()
        log.info("SensorSession: stopped.")

    # ── private helpers ─────────────────────────────────────────────────────

    def _connect(self):
        """Use module-level singleton — never reopens DLL."""
        self._hsd_link, self._hsd = _get_hsd_connection(self._acq_folder)
        devices = self._hsd_link.get_devices(self._hsd)
        if not devices:
            raise RuntimeError("No compatible ST devices found over USB.")
        log.info("Device count: %d", len(devices))

    def _enable_microphone(self) -> dict:
        mic = config.SENSOR_NAME
        sensor_names = self._hsd_link.get_sensors_names(self._hsd, config.DEVICE_ID)
        log.info("Sensors on device: %s", sensor_names)

        if mic not in sensor_names:
            raise RuntimeError(f"'{mic}' not found. Available: {sensor_names}")

        enabled = self._hsd_link.get_sensor_enabled(
            self._hsd, config.DEVICE_ID, sensor_name=mic
        )
        if not enabled:
            log.info("Enabling %s …", mic)
            self._hsd_link.set_sensor_enable(
                self._hsd, config.DEVICE_ID, True, sensor_name=mic
            )

        raw = self._hsd_link.get_component_status(self._hsd, config.DEVICE_ID, mic)
        comp_status = raw.get(mic, raw)
        log.info("Mic status: %s", comp_status)
        return comp_status

    def _start_streaming(self, comp_status: dict):
        mic = config.SENSOR_NAME
        usb_dps = comp_status.get("usb_dps")
        if usb_dps is None:
            raise RuntimeError(f"'{mic}' has no usb_dps field: {comp_status}")

        # DataReader parameters from component metadata
        dim = comp_status.get("dim", 1)
        spts = comp_status.get("samples_per_ts", 1000)
        if isinstance(spts, dict):
            spts = spts.get("val", 1000)
        data_type = comp_status.get("data_type", "int16")
        sample_size = TypeConversion.check_type_length(data_type)
        format_char = TypeConversion.get_format_char(data_type)
        sensitivity = comp_status.get("sensitivity", 1.0 / 32768.0)

        # Output callback for DataReader
        def on_decoded_data(data_obj: DataClass):
            if data_obj.data and 0 in data_obj.data:
                samples = data_obj.data[0].astype(np.float32)
                self.audio_buffer.push(samples)

        data_reader = DataReader(
            output_function=on_decoded_data,
            comp_name=mic,
            samples_per_ts=spts,
            dimensions=dim,
            sample_size=sample_size,
            data_format=format_char,
            sensitivity=sensitivity,
            interleaved_data=True,
            flat_raw_data=False,
        )

        log.info("Starting FW log (usb_dps=%d, spts=%d, sensitivity=%g) ...",
                 usb_dps, spts, sensitivity)
        self._hsd_link.start_log(self._hsd, config.DEVICE_ID)

        self._stop_event.clear()
        self._stream_thread = _MicStreamThread(
            stop_event   = self._stop_event,
            hsd          = self._hsd,
            device_id    = config.DEVICE_ID,
            comp_name    = mic,
            usb_dps      = usb_dps,
            data_reader  = data_reader,
            acq_folder   = self._acq_folder,
        )
        self._stream_thread.start()


# ══════════════════════════════════════════════════════════════════════════════
# Microphone streaming thread
# ══════════════════════════════════════════════════════════════════════════════

class _MicStreamThread(Thread):
    """
    Polls hsd.get_sensor_data() every 20 ms and feeds payloads to DataReader.
    DataReader strips timestamps and pushes scaled float32 samples to buffer.
    """

    def __init__(
        self,
        stop_event:   Event,
        hsd,
        device_id:    int,
        comp_name:    str,
        usb_dps:      int,
        data_reader:  DataReader,
        acq_folder:   str,
    ):
        super().__init__(name="MicStreamThread", daemon=True)
        self.stop_event   = stop_event
        self.hsd          = hsd
        self.device_id    = device_id
        self.comp_name    = comp_name
        self.usb_dps      = usb_dps
        self.data_reader  = data_reader
        self.acq_folder   = acq_folder
        self._prev_cnt    = 0
        self._dat_file    = None

    def run(self) -> None:
        dat_path = os.path.join(self.acq_folder, f"{self.comp_name}.dat")
        try:
            self._dat_file = open(dat_path, "wb")
        except OSError as e:
            log.warning("Cannot open .dat file: %s", e)

        packet_span = self.usb_dps + 4
        packets_processed = 0

        while not self.stop_event.wait(0.02):
            try:
                res = self.hsd.get_sensor_data(self.device_id, self.comp_name)
            except Exception as exc:
                log.warning("get_sensor_data error: %s", exc)
                continue

            if res is None:
                continue
            _, raw_blob = res
            if not raw_blob:
                continue

            if self._dat_file and not self._dat_file.closed:
                self._dat_file.write(raw_blob)

            packet_count = len(raw_blob) // packet_span
            for p_idx in range(packet_count):
                base      = p_idx * packet_span
                cnt_bytes = raw_blob[base: base + 4]
                payload   = raw_blob[base + 4: base + packet_span]

                self._prev_cnt = struct.unpack("=i", cnt_bytes)[0]

                # Feed payload to DataReader (strips 8-byte timestamps & scales)
                self.data_reader.feed_data(DataClass(self.comp_name, payload))
                packets_processed += 1

            if packets_processed > 0 and packets_processed % 50 == 0:
                log.info("MicStreamThread: %d packets processed ...", packets_processed)

        if self._dat_file and not self._dat_file.closed:
            self._dat_file.close()
        log.info("MicStreamThread: exited (%d packets processed).", packets_processed)


# ══════════════════════════════════════════════════════════════════════════════
# Public factories
# ══════════════════════════════════════════════════════════════════════════════

def create_sensor_session() -> tuple:
    buf     = RollingAudioBuffer(max_samples=config.SENSOR_SAMPLE_RATE * 3)
    session = SensorSession(buf)
    return buf, session


# ══════════════════════════════════════════════════════════════════════════════
# PC Microphone Session (sounddevice)
# ══════════════════════════════════════════════════════════════════════════════

class PCMicSession:
    """Live microphone session using PC / laptop built-in microphone."""

    def __init__(self, audio_buffer: RollingAudioBuffer, sample_rate: int = config.MODEL_SAMPLE_RATE):
        self.audio_buffer = audio_buffer
        self.sample_rate  = sample_rate
        self.connected    = False
        self.error_msg    = ""
        self._stream      = None

    def start(self) -> bool:
        try:
            import sounddevice as sd

            def audio_callback(indata, frames, time_info, status):
                mono = indata[:, 0].astype(np.float32)
                self.audio_buffer.push(mono)

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=audio_callback,
                blocksize=1024,
            )
            self._stream.start()
            self.connected = True
            self.error_msg = ""
            log.info("PCMicSession: started listening on default microphone (%d Hz) ✔", self.sample_rate)
            return True
        except Exception as exc:
            self.error_msg = str(exc)
            self.connected = False
            log.error("PCMicSession.start failed: %s", exc)
            return False

    def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.connected = False
        self.audio_buffer.clear()
        log.info("PCMicSession: stopped.")


def create_pcmic_session() -> tuple:
    buf     = RollingAudioBuffer(max_samples=config.MODEL_SAMPLE_RATE * 3)
    session = PCMicSession(buf)
    return buf, session

