# -*- coding: utf-8 -*-
# *****************************************************************************
#  * @file    stdatalog_sensors_streaming_common.py
#  * @author  SRA
# ******************************************************************************
# * @attention
# *
# * Copyright (c) 2022 STMicroelectronics.
# * All rights reserved.
# *
# * This software is licensed under terms that can be found in the LICENSE file
# * in the root directory of this software component.
# * If no LICENSE file comes with this software, it is provided AS-IS.
# *
# *
# ******************************************************************************
"""
Shared streaming helper for HSDLink sensor streaming examples.

Why this module exists
----------------------
The repository provides three user-facing entrypoints:

1) `stdatalog_sensors_streaming_usb.py`
2) `stdatalog_sensors_streaming_serial.py`
3) `stdatalog_sensors_streaming.py` (combined/advanced)

All three examples follow the same high-level flow:

1) Create an HSDLink instance
2) Open serial transport when needed
3) Start logging
4) Continuously read and decode packets
5) Persist raw `.dat` files and JSON metadata
6) Stop cleanly

To avoid duplicating this logic in each entrypoint, this helper module keeps
the full implementation in one place and exposes a single API:
`run_streaming_example(...)`.

What is transport-specific vs shared
------------------------------------
- Shared:
    - Device/session lifecycle (start/stop)
    - DataReader creation
    - File persistence
    - Metadata save
- USB/PnPL specific:
    - Polling via `get_sensor_data(...)`
    - One reader thread per sensor component
- Serial specific:
    - Explicit serial port open
    - Polling via `get_serial_data()`
    - One shared reader thread routing by channel id

Design goal
-----------
Keep entrypoint scripts very small and easy to read while still exposing an
exhaustive, realistic implementation for users who need to understand the
full workflow.
"""

import os
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Dict, List, Optional, Tuple

# Add SDK root (three levels up) for local editable installs.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from stdatalog_core.HSD_link.HSDLink import HSDLink
from stdatalog_core.HSD_utils.DataReader import DataReader
from stdatalog_core.HSD.utils.type_conversion import TypeConversion
from stdatalog_pnpl.DTDL.device_template_manager import ComponentType


@dataclass
class DataClass:
    """
    Container passed to the output callback.

    Notes
    -----
    `DataReader.feed_data(...)` will call the user callback with this object.
    Depending on DataReader configuration, `data` may carry raw bytes or a
    decoded dictionary/array structure.
    """

    comp_name: str
    data: bytes


def default_output_function(data: DataClass) -> None:
    """
    Default output callback used by the example entrypoints.

    The user can replace this callback to stream data elsewhere (plotters,
    queues, sockets, databases, custom analytics pipelines, etc.).
    """
    print(f"Component: {data.comp_name}, Data {data.data} bytes\n")


_component_meta: Dict[str, Dict[str, Any]] = {}


def resolve_serial_port(configured_port: Optional[str]) -> str:
    """
    Resolve the serial port used by the serial datalog transport.

    If no port is configured, prefer the first serial port whose USB
    manufacturer contains "STMicroelectronics". If no such port exists and
    exactly one serial port is available, auto-select it.
    """
    # If the user explicitly configured the port, always trust that value.
    # This is the most deterministic option for scripts and CI pipelines.
    if configured_port:
        return configured_port

    from serial.tools import list_ports

    # Read all serial ports visible to the OS.
    available_port_infos = list(list_ports.comports())

    # First heuristic (preferred): pick the first STMicroelectronics USB device.
    # This is the most common case when one ST board is connected.
    for port in available_port_infos:
        manufacturer = getattr(port, "manufacturer", None) or ""
        if "stmicroelectronics" in manufacturer.lower():
            print(f"Using STMicroelectronics serial port: {port.device}")
            return port.device

    # Second heuristic: keep only ports that look like real USB serial devices.
    # This filters out pseudo ports such as debug-console/Bluetooth endpoints.
    candidate_port_infos = []
    for port in available_port_infos:
        manufacturer = getattr(port, "manufacturer", None)
        product = getattr(port, "product", None)
        description = getattr(port, "description", None) or ""
        device = getattr(port, "device", "")
        if (
            getattr(port, "vid", None) is not None
            or manufacturer is not None
            or product is not None
            or "usb" in description.lower()
            or "usb" in device.lower()
        ):
            candidate_port_infos.append(port)

    candidate_ports = [port.device for port in candidate_port_infos]

    # If exactly one reasonable candidate exists, auto-select it.
    if len(candidate_ports) == 1:
        selected_port = candidate_ports[0]
        print(f"Using auto-detected serial port: {selected_port}")
        return selected_port

    # If no candidates are found, provide an explicit actionable error.
    if not candidate_ports:
        raise RuntimeError(
            'No compatible serial ports found. Connect the board or set COM_PORT explicitly.'
        )

    # Multiple candidates remain: require explicit user choice for safety.
    raise RuntimeError(
        'Multiple compatible serial ports found. Set COM_PORT when DEV_COM_TYPE is "st_serial_datalog".'
    )


def resolve_serial_timeout(configured_timeout: Optional[float]) -> Optional[float]:
    """
    Resolve the serial read timeout used by the serial transport.

    We expose this function to keep timeout policy centralized. Right now it
    simply forwards the configured value, but this is a convenient hook if a
    future release wants to enforce defaults by OS/platform.
    """
    return configured_timeout


def is_serial_datalog(dev_com_type: str) -> bool:
    """
    Return True when the selected transport string is serial datalog.

    This function checks the *requested* backend type, not necessarily the
    backend that the HSDLink factory eventually returns.
    """
    return dev_com_type == "st_serial_datalog"


def uses_serial_transport(hsd_link: Any) -> bool:
    """
    Return True when the created link instance uses serial transport.

    Important distinction:
    - Requested type (`dev_com_type`) can be `st_hsd`
    - Returned link can still be serial when the factory falls back

    We detect serial by capability (presence of `get_serial_data`) instead of
    requested string to keep behavior correct across fallback scenarios.
    """
    return hasattr(hsd_link, "get_serial_data")


def register_component_metadata(comp_name: str, status: dict) -> None:
    """
    Extract and store decoding metadata for a component.

    The current examples do not consume all this metadata directly, but keeping
    it cached makes it straightforward to extend callbacks with richer context
    (units, dimensions, sample size, etc.).
    """
    data_type = status.get("data_type")
    if data_type is None:
        return
    _component_meta[comp_name] = {
        "dimensions": status.get("dim", 1),
        "sensitivity": status.get("sensitivity", 1.0),
        "samples_per_ts": status.get("samples_per_ts", 1),
        "data_type": data_type,
        "format_char": TypeConversion.get_format_char(data_type),
        "sample_size": TypeConversion.check_type_length(data_type),
    }


class DataSourceStreamingThread(Thread):
    """
    USB/PnPL per-component streaming thread.

    Model:
    - One thread per enabled sensor component
    - Poll `get_sensor_data(device_id, component_name)`
    - Parse packet counter + payload framing
    - Forward payload to DataReader
    - Append raw bytes to `.dat` file
    """

    def __init__(
        self,
        stop_event: Event,
        hsd_link: HSDLink,
        data_reader: DataReader,
        device_id: int,
        component_name: str,
        data_file,
        usb_dps: int,
        show_packet_loss_warnings: bool,
    ) -> None:
        super().__init__(name=f"StreamThread-{component_name}", daemon=True)
        self.stop_event = stop_event
        self.hsd_link = hsd_link
        self.data_reader = data_reader
        self.device_id = device_id
        self.component_name = component_name
        self.data_file = data_file
        self.usb_dps = usb_dps
        self.show_packet_loss_warnings = show_packet_loss_warnings
        self.prev_cnt = 0

    def run(self) -> None:
        # For USB packets, firmware prepends a 4-byte counter to each payload.
        # The script uses this to detect packet loss.
        packet_span = self.usb_dps + 4
        while not self.stop_event.wait(0.02):
            # Poll one blob from the selected sensor component.
            res = self.hsd_link.get_sensor_data(self.device_id, self.component_name)
            if res is None:
                continue
            _, raw_blob = res
            if not raw_blob:
                continue

            # One blob may contain multiple complete packets back-to-back.
            packet_count = len(raw_blob) // packet_span
            for p_idx in range(packet_count):
                base = p_idx * packet_span
                cnt_bytes = raw_blob[base : base + 4]
                payload_bytes = raw_blob[base + 4 : base + packet_span]
                curr_cnt = struct.unpack("=i", cnt_bytes)[0]

                # Packet-loss check: counter delta should match expected payload size.
                diff = curr_cnt - self.prev_cnt
                if self.show_packet_loss_warnings and curr_cnt != 0 and diff != self.usb_dps:
                    lost_packets = diff // self.usb_dps
                    print(
                        f"[WARN] {self.component_name}: "
                        f"{int(lost_packets)} packet(s) lost ({diff} bytes)."
                    )

                self.prev_cnt = curr_cnt

                # Feed payload to DataReader; this triggers user callback.
                self.data_reader.feed_data(DataClass(self.component_name, payload_bytes))

            # Persist the full raw blob as-is for offline tooling compatibility.
            self.data_file.write(raw_blob)


class SerialDataStreamingThread(Thread):
    """
    Shared serial streaming thread routing packets by serial channel.

    Model:
    - Single thread for all serial channels
    - Poll `get_serial_data()`
    - Route packets by `pkt.header.ch_num`
    - Feed each channel payload to matching DataReader

    Why one thread?
    Serial delivers one packet stream carrying all channels multiplexed.
    """

    def __init__(
        self,
        stop_event: Event,
        hsd_link: HSDLink,
        show_packet_loss_warnings: bool,
        data_reader_params: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(name="StreamThread-serial", daemon=True)
        self.stop_event = stop_event
        self.hsd_link = hsd_link
        self.show_packet_loss_warnings = show_packet_loss_warnings
        self.data_reader_params = data_reader_params if data_reader_params is not None else {}
        self.prev_cnts = {channel: 0 for channel in self.data_reader_params}

    def update_data_reader_params(self, data_reader_params: Dict[int, Dict[str, Any]]) -> None:
        """
        Install or refresh channel-to-component routing map.

        The map is prepared after reading device status because we need
        component metadata first.
        """
        self.data_reader_params = data_reader_params
        for channel in data_reader_params:
            self.prev_cnts.setdefault(channel, 0)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                # Poll next serial packet from transport manager.
                pkt = self.hsd_link.get_serial_data()
            except Exception as e:
                # During shutdown, port closure can race with read loop.
                # If shutdown is ongoing or port is already closed, exit quietly.
                com_manager = self.hsd_link.get_com_manager()
                serial_port = getattr(com_manager, "serial_port", None)
                if self.stop_event.is_set() or serial_port is None or not getattr(serial_port, "is_open", False):
                    break
                # Unexpected runtime transport failure: print warning and stop.
                print(f"[WARN] Serial receiver stopped due to transport error: {e}")
                break

            # Ignore non-packet/no-data conditions.
            if pkt is None or getattr(pkt, "header", None) is None:
                continue

            data = pkt.data or b""
            if pkt.header.cr != 0 or len(data) <= 4:
                continue

            # Route by channel number.
            channel = pkt.header.ch_num
            channel_info = self.data_reader_params.get(channel)
            if channel_info is None:
                # Channel not configured in this session: ignore safely.
                continue

            curr_cnt = struct.unpack("=i", data[0:4])[0]
            payload_len = len(data) - 4
            diff = curr_cnt - self.prev_cnts[channel]
            if self.show_packet_loss_warnings and curr_cnt != 0 and diff != payload_len:
                lost_packets = diff // payload_len if payload_len else 0
                print(
                    f"[WARN] {channel_info['comp_name']}: "
                    f"{int(lost_packets)} packet(s) lost ({diff} bytes)."
                )

            # Feed decoded payload to the component DataReader callback chain.
            channel_info["data_reader"].feed_data(
                DataClass(channel_info["comp_name"], data[4:])
            )

            # Persist full packet (counter + payload) for serial compatibility.
            data_file = channel_info.get("file")
            if data_file is not None and not data_file.closed:
                data_file.write(data)

            self.prev_cnts[channel] = curr_cnt


class LogController:
    """
    Coordinates streaming threads, logging control, and file persistence.

    This class is intentionally transport-aware but API-stable:
    - `start(...)` and `stop(...)` are the only lifecycle calls
    - Internal helpers select USB or serial behavior as needed
    """

    def __init__(
        self,
        hsd_link: HSDLink,
        output_fn: Callable[[DataClass], None],
        show_packet_loss_warnings: bool,
    ) -> None:
        self.hsd_link = hsd_link
        self.output_fn = output_fn
        self.show_packet_loss_warnings = show_packet_loss_warnings
        self.data_readers: List[DataReader] = []
        self.threads: List[Thread] = []
        self.stop_flags: List[Event] = []
        self.open_files: List[Any] = []
        self.log_started = False
        self.serial_transport = uses_serial_transport(hsd_link)
        self.serial_thread: Optional[SerialDataStreamingThread] = None

    def _ensure_serial_receiver_started(self) -> None:
        # Serial command responses are processed through the same receive path.
        # The receiver must be alive before issuing status/log commands.
        if self.serial_thread is not None:
            return

        stop_flag = Event()
        self.stop_flags.append(stop_flag)
        self.serial_thread = SerialDataStreamingThread(
            stop_flag,
            self.hsd_link,
            self.show_packet_loss_warnings,
        )
        self.serial_thread.start()
        self.threads.append(self.serial_thread)

    def _get_enabled_sensor_components(self, device_status: dict) -> List[Tuple[str, dict]]:
        # Keep only enabled SENSOR components; skip algorithms/actuators.
        stream_components: List[Tuple[str, dict]] = []
        for comp in device_status["components"]:
            comp_name = next(iter(comp))
            comp_status = comp[comp_name]
            if comp_status.get("c_type") != ComponentType.SENSOR.value:
                continue
            if not comp_status.get("enable", False):
                continue
            stream_components.append((comp_name, comp_status))
        return stream_components

    def _create_data_reader(self, comp_name: str, comp_status: dict) -> DataReader:
        # Normalize component status into DataReader constructor parameters.
        dimensions = comp_status.get("dim", 1)
        sensitivity = comp_status.get("sensitivity", 1)
        samples_per_ts = comp_status.get("samples_per_ts", 1)
        if isinstance(samples_per_ts, dict):
            samples_per_ts = samples_per_ts.get("val", 1)
        data_type = comp_status.get("data_type")
        sample_size = TypeConversion.check_type_length(data_type)
        format_char = TypeConversion.get_format_char(data_type)

        # Cache metadata in case callbacks/tooling need this context.
        register_component_metadata(comp_name, comp_status)

        dr = DataReader(
            self.output_fn,
            comp_name,
            samples_per_ts,
            dimensions,
            sample_size,
            format_char,
            sensitivity,
            True,
            False,
        )
        self.data_readers.append(dr)
        return dr

    def _start_usb_streaming(self, device_id: int, stream_components: List[Tuple[str, dict]]) -> None:
        # USB path: one dedicated thread per component.
        for comp_name, c_status in stream_components:
            usb_dps = c_status.get("usb_dps")
            if usb_dps is None:
                print(f"[SKIP] {comp_name}: missing usb_dps.")
                continue

            dr = self._create_data_reader(comp_name, c_status)
            dat_path = Path(self.hsd_link.get_acquisition_folder()) / f"{comp_name}.dat"
            data_file = dat_path.open("wb")
            self.open_files.append(data_file)

            stop_flag = Event()
            self.stop_flags.append(stop_flag)
            thread = DataSourceStreamingThread(
                stop_flag,
                self.hsd_link,
                dr,
                device_id,
                comp_name,
                data_file,
                usb_dps,
                self.show_packet_loss_warnings,
            )
            thread.start()
            self.threads.append(thread)

    def _start_serial_streaming(self, stream_components: List[Tuple[str, dict]]) -> None:
        # Serial path: build channel map for the shared serial receiver.
        data_reader_params: Dict[int, Dict[str, Any]] = {}
        for channel, (comp_name, c_status) in enumerate(stream_components):
            dr = self._create_data_reader(comp_name, c_status)
            dat_path = Path(self.hsd_link.get_acquisition_folder()) / f"{comp_name}.dat"
            data_file = dat_path.open("wb")
            self.open_files.append(data_file)
            data_reader_params[channel] = {
                "comp_name": comp_name,
                "data_reader": dr,
                "file": data_file,
            }

        self._ensure_serial_receiver_started()
        self.serial_thread.update_data_reader_params(data_reader_params)

    def start(self, device_id: int) -> None:
        # Start sequence:
        # 1) Ensure receiver thread (serial only)
        # 2) Read device status and enabled components
        # 3) Start FW logging with transport-specific interface id
        # 4) Start data reader thread(s)
        print("Starting logging...")
        if self.serial_transport:
            self._ensure_serial_receiver_started()

        status = self.hsd_link.get_device_status(device_id)
        device_status = status["devices"][device_id]
        stream_components = self._get_enabled_sensor_components(device_status)
        if not stream_components:
            print("[WARN] No enabled sensor components found.")
            return

        # Interface id differs by transport in current firmware protocols.
        interface = 3 if self.serial_transport else 1
        self.hsd_link.start_log(device_id, interface=interface)
        self.log_started = True

        if self.serial_transport:
            self._start_serial_streaming(stream_components)
        else:
            self._start_usb_streaming(device_id, stream_components)

    def stop(self, device_id: int) -> None:
        # Stop sequence is careful on serial because command path and data path
        # share the same underlying transport.
        print("Stopping logging...")
        if self.log_started:
            try:
                self.hsd_link.stop_log(device_id)
            except Exception as e:
                print(f"[WARN] stop_log failed: {e}")

        if not self.log_started:
            # If logging never started, just stop threads and close files.
            for ev in self.stop_flags:
                ev.set()
            for t in self.threads:
                t.join(timeout=2)
            for f in self.open_files:
                try:
                    f.close()
                except Exception as e:
                    print(f"[WARN] file close failed: {e}")
            return

        try:
            # Save full device configuration JSON snapshot.
            self.hsd_link.save_json_device_file(device_id)
        except Exception as e:
            print(f"[WARN] save_json_device_file failed: {e}")

        try:
            # Save acquisition metadata JSON (name, times, format, interface...).
            self.hsd_link.save_json_acq_info_file(device_id)
        except Exception as e:
            print(f"[WARN] save_json_acq_info_file failed: {e}")

        if self.serial_transport:
            try:
                # During teardown, suppress expected low-level transport noise.
                self.hsd_link.get_com_manager().set_suppress_errors(True)
            except Exception as e:
                print(f"[WARN] failed to suppress serial transport errors: {e}")

        for ev in self.stop_flags:
            ev.set()

        if self.serial_transport:
            try:
                # Close serial port explicitly to unblock receiver read loop.
                self.hsd_link.close()
            except Exception as e:
                print(f"[WARN] serial close failed during shutdown: {e}")

        for t in self.threads:
            t.join(timeout=2)

        for f in self.open_files:
            try:
                f.close()
            except Exception as e:
                print(f"[WARN] file close failed: {e}")


def run_streaming_example(
    acquisition_folder: str,
    device_id: int,
    duration: float,
    dev_com_type: str,
    output_fn: Optional[Callable[[DataClass], None]] = None,
    com_port: Optional[str] = None,
    com_speed: int = 1843200,
    timeout: Optional[float] = None,
    show_packet_loss_warnings: bool = True,
) -> None:
    """
    Run streaming example using selected HSDLink transport.

    This is the single public API used by all entrypoint scripts.
    It handles:
    - link creation
    - transport detection/fallback notice
    - optional serial open
    - controller lifecycle start/stop
    """
    hsd_link = HSDLink()
    # The factory may return a different backend than requested when fallback
    # logic is enabled (for example, requested `st_hsd` -> returned serial).
    hsd = hsd_link.create_hsd_link(
        dev_com_type=dev_com_type,
        acquisition_folder=acquisition_folder,
    )
    if hsd is None:
        print("Failed to create HSDLink instance.")
        return

    serial_transport = uses_serial_transport(hsd)
    if serial_transport and not is_serial_datalog(dev_com_type):
        # Inform users when fallback selected a different transport backend.
        print(
            'Requested DEV_COM_TYPE="st_hsd", but the factory selected '
            '"st_serial_datalog" as fallback.'
        )

    if serial_transport:
        # Serial requires explicit port open before commands/streaming.
        serial_port = resolve_serial_port(com_port)
        serial_timeout = resolve_serial_timeout(timeout)
        print(
            f"Opening serial link on {serial_port} "
            f"at {com_speed} baud (timeout={serial_timeout})..."
        )
        hsd.open(serial_port, com_speed, timeout=serial_timeout)

    controller = LogController(
        hsd,
        output_fn if output_fn is not None else default_output_function,
        show_packet_loss_warnings,
    )
    try:
        # Start threads + FW logging, then keep session alive for `duration`.
        controller.start(device_id=device_id)
        time.sleep(duration)
    finally:
        # Always attempt controlled shutdown (even on KeyboardInterrupt/errors).
        controller.stop(device_id=device_id)
