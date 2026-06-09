#!/usr/bin/env python
# coding: utf-8
# *****************************************************************************
#  * @file    HelloWorldPlugin.py
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
"""Simple HelloWorld Data Toolkit plugin.

This tutorial plugin demonstrates the minimal structure of an `HSD_Plugin` by
printing incoming data to stdout. It does not provide a plot widget; instead,
it logs the component name, data payload, and timestamp for each processed
packet.
"""

from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin

class PluginClass(HSD_Plugin):
    """Tutorial plugin that echoes incoming data to stdout.

    Useful for understanding plugin lifecycle and data flow in the Data Toolkit.
    """

    def __init__(self):
        """Initialize the HelloWorld plugin state.

        Prints a simple initialization message; no additional state required.
        """
        super().__init__()
        print("HelloWorldPlugin has been initialized!")

    def process(self, data):
        """Process a single data object, printing its contents.

        Parameters
        ----------
        data : HSD_DataToolkit_data
            The incoming data object with `comp_name`, `data`, and `timestamp`.

        Returns
        -------
        HSD_DataToolkit_data
            The same data object, unchanged.
        """
        print("HelloWorldPlugin process method called")
        print(f"---> Received data from: {data.comp_name}")
        print(f"-----> Data: {data.data}")
        print(f"-----> Timestamp: {data.timestamp}")
        return data

    def create_plot_widget(self):
        """No plot widget for this tutorial plugin.

        Prints a message and returns ``None``.

        Returns
        -------
        None
        """
        print("HelloWorldPlugin create_plot_widget method called")
