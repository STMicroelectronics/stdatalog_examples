# -*- coding: utf-8 -*-
# *****************************************************************************
#  * @file    stdatalog_sensors_streaming_usb.py
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
USB/PnPL streaming example for HSDLink.

This entrypoint keeps the example focused on the standard HSD USB workflow.
For serial datalog transports, use `stdatalog_sensors_streaming_serial.py`.

Why this file exists
--------------------
This file intentionally hides serial-specific complexity (serial port
selection/open, serial channel routing, serial shutdown handling) so users can
learn the USB/PnPL path first.

Internally
----------
All heavy logic is implemented in `stdatalog_sensors_streaming_common.py`.
This file only sets USB-oriented configuration and calls the shared runner.
"""

import os
import sys

# Add SDK root (three levels up) for local editable installs.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from stdatalog_examples.cli_applications.stdatalog_sensors_streaming.stdatalog_sensors_streaming_common import (
    DataClass,
    run_streaming_example,
)

ACQUISITIONS_CONTAINER_FOLDER: str = "./test_streaming"
LOG_DURATION_SEC: float = 3.0
SHOW_PACKET_LOSS_WARNINGS: bool = True
# USB script deliberately does not expose COM_PORT/COM_SPEED/TIMEOUT settings.


def output_function(data: DataClass) -> None:
    """
    Default callback for decoded data.

    Replace this callback to plug your own processing while keeping
    acquisition/transport handling unchanged.
    """
    print(f"Component: {data.comp_name}, Data {data.data} bytes\n")


def main(
    acquisition_folder: str = ACQUISITIONS_CONTAINER_FOLDER,
    device_id: int = 0,
    duration: float = LOG_DURATION_SEC,
) -> None:
    """
    Run the USB/PnPL streaming example.

    Key choice here is `dev_com_type="st_hsd"`, which asks the helper to use
    USB/PnPL backend first.
    """
    run_streaming_example(
        acquisition_folder=acquisition_folder,
        device_id=device_id,
        duration=duration,
        dev_com_type="st_hsd",
        output_fn=output_function,
        show_packet_loss_warnings=SHOW_PACKET_LOSS_WARNINGS,
    )


if __name__ == "__main__":
    # Script-style execution for quick local runs.
    main()