#!/usr/bin/env python
# coding: utf-8
# *****************************************************************************
#  * @file    ProcessPlugin.py
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
"""Process plugin for chained Data Toolkit tutorials.

Checks accelerometer samples from component `iis3dwb_acc` and prints a warning when any value
exceeds a configurable threshold. The plugin forwards the data unchanged, acting as a pure
checker in a chained pipeline.
"""

import numpy as np

from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin

class PluginClass(HSD_Plugin):
    """Monitors accelerometer data and warns on threshold exceedance.

    The plugin performs a simple check without altering the incoming data object, making it
    suitable for chained processing where subsequent plugins rely on unmodified inputs.
    """

    def __init__(self):
        """Initialize the process plugin.

        Parameters:
        - None

        Returns:
        - None
        """
        super().__init__()
        # Threshold used to flag samples.
        self.control_thr = 1.7
        print("ProcessPlugin has been initialized!")

    def process(self, data):
        """Inspect incoming data and warn if threshold is exceeded.

        Parameters:
        - data (HSD_DataToolkit_data): Input with `comp_name` (str) and `data` (numpy array).

        Returns:
        - HSD_DataToolkit_data: The same `data` object, unmodified.
        """
        if data.comp_name == "iis3dwb_acc":
            if np.any(data.data >= self.control_thr):
                print("Warning data above threshold !!")
        return data

    def create_plot_widget(self):
        """Create the plugin's plot widget (not implemented).

        Returns:
        - None
        """
        print("ProcessPlugin create_plot_widget method called")
