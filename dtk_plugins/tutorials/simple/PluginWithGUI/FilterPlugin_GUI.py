#!/usr/bin/env python
# coding: utf-8
# *****************************************************************************
#  * @file    FilterPlugin_GUI.py
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
"""Filter plugin with GUI for accelerometer data visualization.

This tutorial plugin multiplies accelerometer samples by sensor sensitivity and
computes the vector norm across axes (x, y, z). It displays the resulting
signal in a simple line plot using the Data Toolkit plot widget.
"""

import numpy as np

from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin
from stdatalog_gui.Widgets.Plots.PluginPlotWidget import PluginPlotWidget, PluginPlotType

class PluginClass(HSD_Plugin):
    """Filter accelerometer data and show norm in a line plot.

    Reads `iis3dwb_acc` component data, applies sensitivity scaling, computes
    the Euclidean norm across axes, forwards it to the plot widget, and passes
    the processed data downstream.
    """

    def __init__(self):
        """Initialize plugin and sensitivity cache.

        Sets `sensitivity` to ``None``; it's retrieved lazily from
        `components_status` when first processing data.
        """
        super().__init__()
        self.sensitivity = None
        print("FilterPlugin has been initialized!")

    def process(self, data):
        """Scale accelerometer data and compute vector norm.

        Parameters
        ----------
        data : HSD_DataToolkit_data
            Input data containing accelerometer samples for component
            ``"iis3dwb_acc"``.

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

            # Calculate the squared sum of the accelerometer data
            acc_data_squared_sum = acc_x**2 + acc_y**2 + acc_z**2

            # Calculate the norm of the accelerometer data
            acc_data_norm = np.sqrt(acc_data_squared_sum)

            # Add data to the Plot Widget
            self.plot_widget.add_data([acc_data_norm])

            # Update the data with the calculated norm
            data.data = acc_data_norm
        return data

    def create_plot_widget(self):
        """Create and return a 1D line plot widget for filtered output.

        Returns
        -------
        PluginPlotWidget.LinesWidget
            The plot widget configured for the plugin output.
        """
        print("FilterPlugin create_plot_widget method called")
        self.plot_widget = PluginPlotWidget.create_plot(
            "FilterPlugin", PluginPlotType.LINE, dimension=1
        )
        return self.plot_widget
