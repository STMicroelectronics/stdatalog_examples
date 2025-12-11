# -*- coding: utf-8 -*-
"""
Reusable example: threaded high-speed data streaming via HSDLink.

Key features:
- Per–sensor streaming thread with packet loss detection.
- Real-time data decoding with flexible output callback.
- File persistence of raw .dat data alongside JSON metadata.
- Configurable logging duration and acquisition folder.
- Support for multiple sensor components.
- Clean shutdown and resource management.

This script demonstrates how to set up a threaded data streaming
application using the STDatalog SDK.
It connects to an HSDatalog-compatible device, starts logging,
streams data from all active sensor components in dedicated threads,
decodes the data in real-time, and persists raw data to disk.
It also handles clean shutdown and saves JSON metadata files.
Users can customize the output_function to process or analyze
the decoded data as needed.
Key Configuration Parameters:
- ACQUISITIONS_CONTAINER_FOLDER: Target folder for HSD acquisitions.
- LOG_DURATION_SEC: Duration of continuous logging in seconds.
- PRINT_FLOAT_PRECISION: Decimal precision for float outputs.
- SHOW_PACKET_LOSS_WARNINGS: Toggle packet loss warnings.
- APPLY_SENSITIVITY: Whether to apply sensor sensitivity to decoded values.
- FLUSH_PRINT_EVERY: Frequency of printed output rows.
"""

import sys
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Thread, Event
from typing import Callable, Dict, List, Any

# Add SDK root (two levels up) for local editable installs.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from stdatalog_core.HSD_link.HSDLink import HSDLink
from stdatalog_core.HSD_utils.DataReader import DataReader
from stdatalog_pnpl.DTDL.device_template_manager import ComponentType
from stdatalog_core.HSD.utils.type_conversion import TypeConversion

# ------------------------------------------------------------------------------------
# Configuration (adjust to user needs)
# ------------------------------------------------------------------------------------
ACQUISITIONS_CONTAINER_FOLDER: str = "./test_streaming"  # Target folder for HSD acquisitions (.dat and JSON files)
LOG_DURATION_SEC: float = 3.0          # Default continuous logging duration
PRINT_FLOAT_PRECISION: int = 6         # Float columns precision
SHOW_PACKET_LOSS_WARNINGS: bool = True # Toggle packet loss messages
APPLY_SENSITIVITY: bool = True         # Multiply decoded values by sensitivity
FLUSH_PRINT_EVERY: int = 1             # Print every N decoded sample rows (1 = all)
# ------------------------------------------------------------------------------------

@dataclass
class DataClass:
    """
    Container passed to output_function.

    comp_name: Name of component/sensor.
    data: Raw bytes OR decoded numeric sequence depending on pipeline stage.
    """
    comp_name: str
    data: bytes


# ============================================================================================
# [!!!] USER-DEFINED OUTPUT FUNCTION [!!!]. Customize according to your needs.
# ============================================================================================
def output_function(data: DataClass) -> None:
    """
    Consumer callback invoked by DataReader.

    Depending on DataReader configuration, data.data may still be raw bytes.
    This implementation decodes raw bytes if needed, groups per sample,
    and prints columns (X Y Z or generic C0..Cn).

    Here received data are numpy arrays for each axis of the sensor.
    This format, contrary to raw bytes, allows easier data handling
    according to the specific needs of the application.

    You can add any additional processing or handling of the data here.
    For example, you could extract only specific axes or values,
    save the data to a file, or perform some analysis on it.
    """
    print(f"Component: {data.comp_name}, Data {data.data} bytes\n")
# ============================================================================================

# Runtime registry holding per-component decoding metadata.
_component_meta: Dict[str, Dict[str, Any]] = {}

def register_component_metadata(comp_name: str, status: dict) -> None:
    """
    Extract and store decoding metadata for a component.

    The DataReader internally handles basic decoding; here we retain
    metadata to enhance output formatting or further processing.
    """
    data_type = status.get("data_type")
    if data_type is None:
        return
    meta = {
        "dimensions": status.get("dim", 1),
        "sensitivity": status.get("sensitivity", 1.0),
        "samples_per_ts": status.get("samples_per_ts", 1),
        "data_type": data_type,
        "format_char": TypeConversion.get_format_char(data_type),
        "sample_size": TypeConversion.check_type_length(data_type),
    }
    _component_meta[comp_name] = meta

class DataSourceStreamingThread(Thread):
    """
    Dedicated streaming thread for one sensor/component.

    Pulls raw USB packets, detects loss using 4-byte counter prefix,
    feeds payload bytes (excluding counter) to DataReader for decode.
    """
    def __init__(
        self,
        stop_event: Event,
        hsd_link: HSDLink,
        data_reader: DataReader,
        device_id: int,
        component_name: str,
        data_file,
        usb_dps: int
    ) -> None:
        super().__init__(name=f"StreamThread-{component_name}", daemon=True)
        self.stop_event = stop_event
        self.hsd_link = hsd_link
        self.data_reader = data_reader
        self.device_id = device_id
        self.component_name = component_name
        self.data_file = data_file   # open binary file handle
        self.usb_dps = usb_dps       # payload bytes per packet (excluding counter)
        self.prev_cnt = 0

    def run(self) -> None:
        """
        Main polling loop. Poll hardware, split concatenated USB packets,
        detect dropped packets, and feed each payload to DataReader.
        """
        packet_span = self.usb_dps + 4  # 4 bytes counter + payload
        while not self.stop_event.wait(0.02):
            res = self.hsd_link.get_sensor_data(self.device_id, self.component_name)
            if res is None:
                continue
            _, raw_blob = res
            if not raw_blob:
                continue

            # How many complete packets are in the blob
            packet_count = len(raw_blob) // packet_span

            for p_idx in range(packet_count):
                base = p_idx * packet_span
                cnt_bytes = raw_blob[base: base + 4]
                payload_bytes = raw_blob[base + 4: base + packet_span]

                # Extract packet counter (little-endian 32-bit signed)
                curr_cnt = struct.unpack("=i", cnt_bytes)[0]

                # Detect packet loss (difference not equal to expected usb_dps offset)
                diff = curr_cnt - self.prev_cnt
                if SHOW_PACKET_LOSS_WARNINGS and curr_cnt != 0 and diff != self.usb_dps:
                    lost_packets = diff // self.usb_dps
                    print(f"[WARN] {self.component_name}: {int(lost_packets)} packet(s) lost ({diff} bytes).")

                self.prev_cnt = curr_cnt

                # Forward payload to DataReader; callback later prints columns
                self.data_reader.feed_data(DataClass(self.component_name, payload_bytes))

            # Persist raw concatenated blob for offline reconstruction
            self.data_file.write(raw_blob)

class LogController:
    """
    Coordinates streaming threads for all active sensor components,
    manages lifecycle and persistence.
    """
    def __init__(self, hsd_link: HSDLink, output_fn: Callable[[DataClass], None]) -> None:
        self.hsd_link = hsd_link
        self.output_fn = output_fn
        self.data_readers: List[DataReader] = []
        self.threads: List[DataSourceStreamingThread] = []
        self.stop_flags: List[Event] = []
        self.open_files: List[Any] = []

    def _create_data_reader(self, comp_name: str, comp_status: dict) -> DataReader:
        """
        Instantiate a DataReader (uses provided callback).
        """
        dimensions = comp_status.get("dim", 1)
        sensitivity = comp_status.get("sensitivity", 1)
        samples_per_ts = comp_status.get("samples_per_ts", 1)
        data_type = comp_status.get("data_type")
        sample_size = TypeConversion.check_type_length(data_type)
        format_char = TypeConversion.get_format_char(data_type)
        interleaved = True
        flat_raw = False

        register_component_metadata(comp_name, comp_status)

        dr = DataReader(
            self.output_fn,
            comp_name,
            samples_per_ts,
            dimensions,
            sample_size,
            format_char,
            sensitivity,
            interleaved,
            flat_raw
        )
        self.data_readers.append(dr)
        return dr

    def start(self, device_id: int) -> None:
        """
        Begin acquisition for all sensor components on the given device.
        """
        print("Starting logging...")
        status = self.hsd_link.get_device_status(device_id)
        device_status = status["devices"][0]
        self.hsd_link.start_log(device_id, 1)

        for comp in device_status["components"]:
            comp_name = list(comp.keys())[0]
            c_status = comp[comp_name]
            c_type = c_status.get("c_type")

            if c_type != ComponentType.SENSOR.value:
                continue

            usb_dps = c_status.get("usb_dps")
            if usb_dps is None:
                print(f"[SKIP] {comp_name}: missing usb_dps.")
                continue

            dr = self._create_data_reader(comp_name, c_status)

            dat_path = Path(self.hsd_link.get_acquisition_folder()) / f"{comp_name}.dat"
            f = dat_path.open("wb")
            self.open_files.append(f)

            stop_flag = Event()
            self.stop_flags.append(stop_flag)

            t = DataSourceStreamingThread(
                stop_flag,
                self.hsd_link,
                dr,
                device_id,
                comp_name,
                f,
                usb_dps
            )
            t.start()
            self.threads.append(t)

    def stop(self, device_id: int) -> None:
        """
        Signal threads to halt, join them, close files, and save JSON metadata.
        """
        print("Stopping logging...")
        try:
            self.hsd_link.stop_log(device_id)
        except Exception as e:
            print(f"[WARN] stop_log failed: {e}")

        for ev in self.stop_flags:
            ev.set()

        for t in self.threads:
            t.join(timeout=2)

        for f in self.open_files:
            try:
                f.close()
            except Exception as e:
                print(f"[WARN] file close failed: {e}")

        try:
            self.hsd_link.save_json_device_file(device_id)
        except Exception as e:
            print(f"[WARN] save_json_device_file failed: {e}")

        try:
            self.hsd_link.save_json_acq_info_file(device_id)
        except Exception as e:
            print(f"[WARN] save_json_acq_info_file failed: {e}")

def main(acquisition_folder: str = ACQUISITIONS_CONTAINER_FOLDER, device_id: int = 0, duration: float = LOG_DURATION_SEC) -> None:
    """
    Entry point: create HSDLink, start streaming, wait duration, then stop.

    acquisition_folder: target path for persisted .dat and JSON metadata.
    device_id: index of device (0 if single connected).
    duration: seconds to stream.
    """
    hsd_link = HSDLink()
    if hsd_link is None:
        print("No compatible devices connected.")
        return

    hsd = hsd_link.create_hsd_link(dev_com_type='st_hsd', acquisition_folder=acquisition_folder)
    if hsd is None:
        print("Failed to create HSDLink instance.")
        return

    controller = LogController(hsd, output_function)
    try:
        controller.start(device_id=device_id)
        time.sleep(duration)
    finally:
        controller.stop(device_id=device_id)

if __name__ == "__main__":
    main()