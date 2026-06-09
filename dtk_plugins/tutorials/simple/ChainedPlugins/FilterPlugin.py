#!/usr/bin/env python
# coding: utf-8
# *****************************************************************************
#  * @file    FilterPlugin.py
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
"""Chained filter plugin for accelerometer data.

This tutorial plugin demonstrates a simple processing stage suitable for a
chained plugin pipeline. It scales accelerometer samples by sensor sensitivity
and computes the vector norm across axes, passing the processed data forward
to subsequent plugins.
"""

import numpy as np

from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin

class PluginClass(HSD_Plugin):
    """Scale accelerometer data and compute the Euclidean norm.

    Designed to be placed before other plugins in a chain, it transforms the
    input accelerometer data (``iis3dwb_acc``) using sensitivity and reduces
    the 3-axis signal to a single norm trace.
    """

    def __init__(self):
        """Initialize plugin and sensitivity cache.

        Sensitivity is resolved lazily from `components_status` on first use.
        """
        super().__init__()
        self.sensitivity = None
        print("FilterPlugin has been initialized!")

    def process(self, data):
        """Scale and reduce accelerometer data to its vector norm.

        Parameters
        ----------
        data : HSD_DataToolkit_data
            Input data object containing samples for component ``iis3dwb_acc``.

        Returns
        -------
        HSD_DataToolkit_data
            The same data object with `data` replaced by the computed norm.
        """
        if data.comp_name == "iis3dwb_acc":

            # Get sensor sensisity
            if self.sensitivity is None:
                self.sensitivity = self.components_status["iis3dwb_acc"]["sensitivity"]

            # Multiply for sensor sensitivity
            data.data = data.data * self.sensitivity

            # Extract the x, y, and z components of the accelerometer data
            acc_x = data.data[0::3]
            acc_y = data.data[1::3]
            acc_z = data.data[2::3]

            # Calculate the norm of the accelerometer data
            acc_data_norm = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
            # Update the data with the calculated norm
            data.data = acc_data_norm
        return data

    def create_plot_widget(self):
        """No UI for this chained plugin; returns ``None``."""
        print("FilterPlugin create_plot_widget method called")
