# -*- coding: utf-8 -*-
# *****************************************************************************
#  * @file    stdatalog_sensors_streaming.py
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
Advanced combined streaming example for HSDLink transports.

This entrypoint keeps the original single-script workflow available while the
shared implementation lives in `stdatalog_sensors_streaming_common.py` and the
transport-specific entrypoints provide simpler USB-only and serial-only views.

How to use this script
----------------------
Use this file when you want one configurable entrypoint that can run both
USB/PnPL and serial datalog transports.

Recommended script selection
----------------------------
- For teaching USB only: `stdatalog_sensors_streaming_usb.py`
- For teaching serial only: `stdatalog_sensors_streaming_serial.py`
- For advanced users who want a single transport-switchable entrypoint:
    this file.

Why this file is still useful
-----------------------------
It demonstrates HSDLink adaptability and backend fallback behavior in one
place while keeping transport internals inside the shared helper.
"""

import os
import sys
from typing import Optional

# Add SDK root (three levels up) for local editable installs.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from stdatalog_examples.cli_applications.stdatalog_sensors_streaming.stdatalog_sensors_streaming_common import (
    DataClass,
    run_streaming_example,
)

# ------------------------------------------------------------------------------------
# Configuration (adjust to user needs)
# ------------------------------------------------------------------------------------
ACQUISITIONS_CONTAINER_FOLDER: str = "./test_streaming"
DEV_COM_TYPE: str = "st_hsd"        # Available values: "st_hsd", "st_serial_datalog"
LOG_DURATION_SEC: float = 3.0
COM_PORT: Optional[str] = None       # Serial port path for "st_serial_datalog"
COM_SPEED: int = 1843200             # Serial baud rate for "st_serial_datalog"
TIMEOUT: Optional[float] = None      # Serial read timeout for "st_serial_datalog"
SHOW_PACKET_LOSS_WARNINGS: bool = True
# Notes:
# - When DEV_COM_TYPE is "st_hsd", the factory may still fall back to serial if
#   no HSD USB board is found.
# - COM_PORT is only used if the selected backend is serial.
# ------------------------------------------------------------------------------------


def output_function(data: DataClass) -> None:
    """
    Default callback for decoded data.

    Replace this function to integrate custom behavior (for example: plot,
    publish on network, save to CSV/Parquet, feed ML model, etc.).
    """
    print(f"Component: {data.comp_name}, Data {data.data} bytes\n")


def main(
    acquisition_folder: str = ACQUISITIONS_CONTAINER_FOLDER,
    device_id: int = 0,
    duration: float = LOG_DURATION_SEC,
    dev_com_type: str = DEV_COM_TYPE,
) -> None:
    """
    Run the combined multi-transport streaming example.

    This function forwards all configuration to the shared helper. The helper
    contains the full transport-specific lifecycle and thread orchestration.
    """
    run_streaming_example(
        acquisition_folder=acquisition_folder,
        device_id=device_id,
        duration=duration,
        dev_com_type=dev_com_type,
        output_fn=output_function,
        com_port=COM_PORT,
        com_speed=COM_SPEED,
        timeout=TIMEOUT,
        show_packet_loss_warnings=SHOW_PACKET_LOSS_WARNINGS,
    )


if __name__ == "__main__":
    # Keep the entrypoint minimal: configuration above, execution here.
    main()
