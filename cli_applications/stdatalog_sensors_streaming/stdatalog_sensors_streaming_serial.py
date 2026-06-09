# -*- coding: utf-8 -*-
# *****************************************************************************
#  * @file    stdatalog_sensors_streaming_serial.py
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
Serial datalog streaming example for HSDLink.

This entrypoint keeps the example focused on the serial-specific workflow:
serial port selection, explicit open, and shared serial packet routing.

Why this file exists
--------------------
Serial transport has operational differences compared to USB (port management,
single multiplexed packet stream, channel routing, teardown nuances). This
entrypoint keeps those concerns visible without mixing them with USB details.

Internally
----------
As with the USB script, this file delegates the heavy logic to
`stdatalog_sensors_streaming_common.py` and only provides serial-oriented
configuration.
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

ACQUISITIONS_CONTAINER_FOLDER: str = "./test_streaming"
LOG_DURATION_SEC: float = 3.0
COM_PORT: Optional[str] = None
COM_SPEED: int = 1843200
TIMEOUT: Optional[float] = None
SHOW_PACKET_LOSS_WARNINGS: bool = True
# Configure COM_PORT explicitly if multiple serial devices are connected.


def output_function(data: DataClass) -> None:
    """
    Default callback for decoded data.

    Replace this callback for custom processing while reusing transport and
    threading behavior from the shared helper.
    """
    print(f"Component: {data.comp_name}, Data {data.data} bytes\n")


def main(
    acquisition_folder: str = ACQUISITIONS_CONTAINER_FOLDER,
    device_id: int = 0,
    duration: float = LOG_DURATION_SEC,
) -> None:
    """
    Run the serial datalog streaming example.

    Key choice here is `dev_com_type="st_serial_datalog"`, which enables
    explicit serial port open and serial packet reader path.
    """
    run_streaming_example(
        acquisition_folder=acquisition_folder,
        device_id=device_id,
        duration=duration,
        dev_com_type="st_serial_datalog",
        output_fn=output_function,
        com_port=COM_PORT,
        com_speed=COM_SPEED,
        timeout=TIMEOUT,
        show_packet_loss_warnings=SHOW_PACKET_LOSS_WARNINGS,
    )


if __name__ == "__main__":
    # Script-style execution for quick local serial runs.
    main()