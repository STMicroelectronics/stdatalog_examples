"""
NotePulse – server.py

WebSocket server (asyncio + websockets library).

Responsibilities
----------------
1. Start the WebSocket server on ws://localhost:8765
2. Accept frontend connections
3. Receive {mode, command} messages from the frontend
4. Manage sensor + audio-processor lifecycle
5. Broadcast prediction JSON to all connected clients every ~250 ms

Message formats
---------------
Frontend → Backend (JSON):
    {"command": "start", "mode": "real"}
    {"command": "start", "mode": "mock"}
    {"command": "stop"}
    {"command": "ping"}

Backend → Frontend (JSON) – normal prediction:
    {
        "timestamp":    1720000000.123,
        "note":         "C4",
        "frequency":    261.63,
        "confidence":   0.94,
        "signal_level": 0.72,
        "status":       "LIVE",          // LIVE | LOW_CONFIDENCE | SILENCE | MOCK | ERROR
        "latency_ms":   38,
        "waveform":     [...200 floats...],
        "all_probs":    {"C4": 0.94, "C5": 0.04, "F5": 0.02},
        "model_info":   {...},
        "sensor_info":  {...},
    }

Backend → Frontend (JSON) – status update:
    {"type": "status", "sensor_connected": true, "mode": "real", ...}

Usage
-----
    python backend/server.py
    python backend/server.py --mock          # mock mode (no hardware)
    python backend/server.py --port 9000     # custom port
"""

import asyncio
import json
import logging
import os
import sys
import time
import argparse
import threading
from typing import Set, Optional

# ── Paths & Virtualenv auto-injection ──────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR  = os.path.join(os.path.dirname(BACKEND_DIR), "shared")
SDK_ROOT    = os.path.abspath(os.path.join(BACKEND_DIR, "..", "..", "stdatalog-pysdk"))

VENV_SITE_PACKAGES = os.path.join(SDK_ROOT, ".venv", "Lib", "site-packages")
EXTRA_PATHS = [
    SHARED_DIR,
    BACKEND_DIR,
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

import config
from model_service import ModelService
from audio_processor import AudioProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger("notepulse.server")

# ══════════════════════════════════════════════════════════════════════════════
# Global state
# ══════════════════════════════════════════════════════════════════════════════

_clients: Set = set()
_clients_lock = threading.Lock()

_model_service:   Optional[ModelService]   = None
_audio_processor: Optional[AudioProcessor] = None
_sensor_session = None          # realtime_sensor.SensorSession or None
_audio_buffer   = None          # realtime_sensor.RollingAudioBuffer or None

_current_mode        = "stopped"   # "real" | "mock" | "stopped"
_last_prediction: dict = {}
_loop: Optional[asyncio.AbstractEventLoop] = None


# ══════════════════════════════════════════════════════════════════════════════
# Prediction callback (called from AudioProcessor thread)
# ══════════════════════════════════════════════════════════════════════════════

def _on_prediction(result: dict) -> None:
    """Called by AudioProcessor on every prediction. Thread-safe."""
    global _last_prediction
    payload = dict(result)
    payload["model_info"]  = _model_service.info() if _model_service else {}
    payload["sensor_info"] = {
        "board":       "SensorTile.box PRO",
        "microphone":  config.SENSOR_NAME,
        "input_sr_hz": config.SENSOR_SAMPLE_RATE,
        "model_sr_hz": config.MODEL_SAMPLE_RATE,
        "connection":  "USB",
        "mode":        _current_mode,
    }
    _last_prediction = payload
    _broadcast_sync(payload)


def _broadcast_sync(payload: dict) -> None:
    """Thread-safe: schedule a broadcast on the asyncio loop."""
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(_broadcast(payload), _loop)


async def _broadcast(payload: dict) -> None:
    """Send payload JSON to all connected WebSocket clients."""
    msg = json.dumps(payload)
    dead = set()
    with _clients_lock:
        clients = set(_clients)
    for ws in clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    if dead:
        with _clients_lock:
            _clients.difference_update(dead)


# ══════════════════════════════════════════════════════════════════════════════
# Monitoring lifecycle
# ══════════════════════════════════════════════════════════════════════════════

def _start_monitoring(mode: str) -> dict:
    """
    Start the sensor session (if mode == 'real') and audio processor.
    Returns a status dict.
    """
    global _audio_processor, _sensor_session, _audio_buffer, _current_mode

    # If already running in the requested mode, avoid tear-down
    if _current_mode == mode and _audio_processor and _audio_processor.is_alive():
        log.info("Monitoring already active in %s mode.", mode)
        return {"started": True, "mode": mode, "already_running": True}

    # Stop any running session first
    _stop_monitoring()

    if mode == "mock":
        _current_mode = "mock"
        _audio_processor = AudioProcessor(
            audio_buffer  = None,
            model_service = _model_service,
            on_prediction = _on_prediction,
            mock_mode     = True,
        )
        _audio_processor.start()
        return {"started": True, "mode": "mock"}

    if mode == "mic":
        _current_mode = "mic"
        try:
            from realtime_sensor import create_pcmic_session
            _audio_buffer, _sensor_session = create_pcmic_session()
            if not _sensor_session.start():
                err = _sensor_session.error_msg
                _current_mode = "stopped"
                return {"started": False, "mode": "mic", "error": err}

            _audio_processor = AudioProcessor(
                audio_buffer  = _audio_buffer,
                model_service = _model_service,
                on_prediction = _on_prediction,
                mock_mode     = False,
                input_sr      = config.MODEL_SAMPLE_RATE,
            )
            _audio_processor.start()
            return {"started": True, "mode": "mic"}
        except Exception as exc:
            log.error("_start_monitoring(mic) failed: %s", exc)
            _current_mode = "stopped"
            return {"started": False, "mode": "mic", "error": str(exc)}

    # Real sensor mode (SensorTile.box PRO over USB)
    _current_mode = "real"
    try:
        from realtime_sensor import create_sensor_session
        _audio_buffer, _sensor_session = create_sensor_session()

        if not _sensor_session.start():
            err = _sensor_session.error_msg
            _current_mode = "stopped"
            msg_err = err
            if "st_serial_datalog" in str(err) or "CommunicationEngineOpenError" in str(err):
                msg_err = (
                    "SensorTile USB buffer locked from prior session. "
                    "Action needed: Unplug USB, switch SensorTile OFF (3 sec) -> ON, and replug. "
                    "Or switch mode to 'PC MIC' to monitor audio immediately."
                )
            return {"started": False, "mode": "real", "error": msg_err}

        _audio_processor = AudioProcessor(
            audio_buffer  = _audio_buffer,
            model_service = _model_service,
            on_prediction = _on_prediction,
            mock_mode     = False,
            input_sr      = config.SENSOR_SAMPLE_RATE,
        )
        _audio_processor.start()
        return {"started": True, "mode": "real"}

    except Exception as exc:
        log.error("_start_monitoring(real) failed: %s", exc)
        _current_mode = "stopped"
        return {"started": False, "mode": "real", "error": str(exc)}


def _stop_monitoring() -> None:
    global _audio_processor, _sensor_session, _current_mode
    if _audio_processor:
        _audio_processor.stop()
        _audio_processor = None
    if _sensor_session:
        _sensor_session.stop()
        # Keep _sensor_session alive so the HSDLink DLL connection is reused!
    _current_mode = "stopped"


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket handler
# ══════════════════════════════════════════════════════════════════════════════

async def _handler(websocket) -> None:
    """Handle one WebSocket connection."""
    with _clients_lock:
        _clients.add(websocket)
    log.info("Client connected. Total: %d", len(_clients))

    # Send current state immediately on connect
    await _send_status(websocket)
    if _last_prediction:
        try:
            await websocket.send(json.dumps(_last_prediction))
        except Exception:
            pass

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            cmd  = msg.get("command", "")
            req_mode = msg.get("mode", "real")
            if req_mode not in ("real", "mock", "mic"):
                req_mode = "real"

            if cmd == "start":
                result = await asyncio.get_event_loop().run_in_executor(
                    None, _start_monitoring, req_mode
                )
                await websocket.send(json.dumps({"type": "start_result", **result}))
                await _broadcast_status()

            elif cmd == "stop":
                await asyncio.get_event_loop().run_in_executor(
                    None, _stop_monitoring
                )
                await websocket.send(json.dumps({"type": "stopped"}))
                await _broadcast_status()

            elif cmd == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

            elif cmd == "get_status":
                await _send_status(websocket)

    except Exception as exc:
        log.debug("Client handler exception: %s", exc)
    finally:
        with _clients_lock:
            _clients.discard(websocket)
        log.info("Client disconnected. Total: %d", len(_clients))


def _make_status_dict() -> dict:
    if _current_mode == "real":
        board = "SensorTile.box PRO"
        mic   = config.SENSOR_NAME
        sr    = config.SENSOR_SAMPLE_RATE
        conn  = "USB (HSDLink)"
    elif _current_mode == "mic":
        board = "PC Audio Device"
        mic   = "Default Microphone"
        sr    = config.MODEL_SAMPLE_RATE
        conn  = "System Audio"
    elif _current_mode == "mock":
        board = "Simulator"
        mic   = "Synthetic Audio"
        sr    = config.MODEL_SAMPLE_RATE
        conn  = "Internal"
    else:
        board = "SensorTile.box PRO"
        mic   = config.SENSOR_NAME
        sr    = config.SENSOR_SAMPLE_RATE
        conn  = "Disconnected"

    return {
        "type":             "status",
        "mode":             _current_mode,
        "sensor_connected": _sensor_session.connected if _sensor_session else False,
        "model_loaded":     _model_service.loaded if _model_service else False,
        "model_info":       _model_service.info() if _model_service else {},
        "sensor_info": {
            "board":       board,
            "microphone":  mic,
            "input_sr_hz": sr,
            "model_sr_hz": config.MODEL_SAMPLE_RATE,
            "connection":  conn,
            "mode":        _current_mode,
        },
        "server_time":      time.time(),
    }


async def _send_status(websocket) -> None:
    try:
        await websocket.send(json.dumps(_make_status_dict()))
    except Exception:
        pass


async def _broadcast_status() -> None:
    await _broadcast(_make_status_dict())


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

async def _main(auto_start_mode: Optional[str]) -> None:
    global _loop, _model_service
    _loop = asyncio.get_event_loop()

    # Load model once at startup
    _model_service = ModelService()
    ok = _model_service.load()
    if not ok:
        log.error("Model load failed: %s", _model_service.error_msg)
        log.error("Path tried: %s", config.MODEL_PATH)
        # Continue anyway – frontend will show MODEL_ERROR

    log.info("Model: %s", _model_service.info())

    import websockets
    log.info(
        "NotePulse WebSocket server listening on ws://%s:%d",
        config.SERVER_HOST, config.SERVER_PORT,
    )

    if auto_start_mode:
        log.info("Auto-starting in %s mode ...", auto_start_mode)
        result = _start_monitoring(auto_start_mode)
        log.info("Auto-start result: %s", result)

    async with websockets.serve(
        _handler,
        config.SERVER_HOST,
        config.SERVER_PORT,
        ping_interval=20,
        ping_timeout=10,
    ):
        await asyncio.Future()   # run forever


def _cleanup_stale_ports():
    import subprocess
    try:
        out = subprocess.check_output('netstat -ano | findstr :8765', shell=True, text=True)
        current_pid = os.getpid()
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and 'LISTENING' in parts:
                pid = int(parts[-1])
                if pid != current_pid:
                    log.info("Terminating stale server process %d on port 8765...", pid)
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
    except Exception:
        pass


def main():
    _cleanup_stale_ports()

    parser = argparse.ArgumentParser(description="NotePulse WebSocket backend")
    parser.add_argument("--mock",   action="store_true",
                        help="Start immediately in mock mode (no SensorTile needed)")
    parser.add_argument("--real",   action="store_true",
                        help="Start immediately in real sensor mode (SensorTile USB)")
    parser.add_argument("--mic",    action="store_true",
                        help="Start immediately using PC built-in microphone")
    parser.add_argument("--port",   type=int, default=config.SERVER_PORT,
                        help=f"WebSocket port (default {config.SERVER_PORT})")
    args = parser.parse_args()

    config.SERVER_PORT = args.port

    auto = None
    if args.mock:
        auto = "mock"
    elif args.mic:
        auto = "mic"
    elif args.real:
        auto = "real"

    import atexit, signal
    atexit.register(_stop_monitoring)
    def _sig_handler(signum, frame):
        log.info("Stopping hardware and exiting...")
        _stop_monitoring()
        sys.exit(0)
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    try:
        asyncio.run(_main(auto_start_mode=auto))
    except KeyboardInterrupt:
        log.info("Shutting down NotePulse server.")
        _stop_monitoring()


if __name__ == "__main__":
    main()
