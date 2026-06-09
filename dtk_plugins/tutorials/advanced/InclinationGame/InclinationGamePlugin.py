#!/usr/bin/env python
# coding: utf-8
# *****************************************************************************
#  * @file    InclinationGamePlugin.py
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
"""Inclination game plugin with scatter plot visualization.

Provides a scatter plot that visualizes a point moving within a rectangular area. The rectangle
border turns red when the point leaves the safe zone, based on a configurable threshold. The
plugin processes accelerometer data from `iis3dwb_acc`, computes mean x/y values, and feeds them
to the plot.
"""

from collections import deque
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QGraphicsRectItem
from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin
from stdatalog_gui.Widgets.Plots.PlotWidget import PlotWidget
from stdatalog_gui.STDTDL_Controller import STDTDL_Controller

class PlotScatterWidget(PlotWidget):
    """
    Scatter plot widget for the inclination game.
    Renders a point within a rectangular area; the border turns red when the point
    reaches the boundaries.
    This class explains how to create a custom plot widget by extending the base
    `PlotWidget` class from the Data Toolkit GUI module.
    
    Methods:
        __init__(self, comp_name, comp_display_name, y0, y1, unit="", p_id=0, parent=None):
        update_plot(self):
        add_data(self, data):
    """

    def __init__(self, comp_name, comp_display_name, y0, y1, unit="", p_id=0, parent=None):
        """Initialize the scatter plot widget.

        Parameters:
        - comp_name (str): Component name.
        - comp_display_name (str): Human-readable component name.
        - y0 (float): Minimum y-axis value.
        - y1 (float): Maximum y-axis value.
        - unit (str): Unit for values (default: "").
        - p_id (int): Plot identifier (default: 0).
        - parent (QWidget | None): Parent widget.

        Returns:
        - None
        """
        controller = STDTDL_Controller()
        super().__init__(controller, comp_name, comp_display_name, p_id, parent, unit)

        self.y0 = y0
        self.y1 = y1
        self.thr = 0.8

        self._data = dict()  # dict of queues
        self._data[0] = deque(maxlen=200000)

        self.scatter = pg.ScatterPlotItem(
            x=[0],
            y=[0],
            pen=pg.mkPen(None),
            brush=pg.mkBrush("#3cb4e6"),
            size=20,
        )

        self.graph_widget.setYRange(self.y0, self.y1, padding=0)
        self.graph_widget.setXRange(self.y0, self.y1, padding=0)

        # Add a rectangular figure
        # x, y, width, height
        self.rect = QGraphicsRectItem(-self.thr, -self.thr, self.thr * 2, self.thr * 2)
        self.rect.setPen(pg.mkPen(color="#a4c238", width=6))
        self.graph_widget.addItem(self.rect)

        # add item to plot window
        self.graph_widget.addItem(self.scatter)

        self.graph_widget.getPlotItem().layout.setContentsMargins(10, 3, 3, 3)
        # Disable right-click menu in plots
        self.graph_widget.getPlotItem().setMenuEnabled(False)
        self.graph_widget.setMinimumSize(QSize(300, 150))

        self.timer_interval_ms = self.timer_interval * 700

    def update_plot(self):
        """Update the scatter plot with the latest data.

        Parameters:
        - None

        Returns:
        - None

        Notes:
        - Pops the latest point from the queue and updates the rectangle color if the threshold
            is exceeded along either axis.
        """
        if len(self._data[0]) > 1:
            data = self._data[0].pop()
            x = data[0]
            y = data[1]
            if np.abs(x[0]) >= self.thr or np.abs(y[0]) >= self.thr:
                self.rect.setPen(pg.mkPen(color="r", width=8))
            else:
                self.rect.setPen(pg.mkPen(color="#a4c238", width=6))

            self.scatter.setData(x, y)
        self.app_qt.processEvents()

    def add_data(self, data):
        """Append a new (x, y) point to the queue.

        Parameters:
        - data (list[list[float]]): Two 1-element lists: `[[x], [y]]`.

        Returns:
        - None
        """
        self._data[0].append(data)

class PluginClass(HSD_Plugin):
    """
    Controls the inclination game for `iis3dwb_acc` data.

    The game renders a point within a rectangular area; the border turns red when the point
    reaches the boundaries. This plugin computes mean x/y values from accelerometer samples and
    pushes them to the plot widget.

    Methods:
        __init__(self): Initializes the PluginClass object.
        start_log_cb(self): Callback method called when logging starts.
        stop_log_cb(self): Callback method called when logging stops.
        tag_cb(self, status, label): Callback method called when a tag is received.
        process(self, data): Processes the input data and returns the processed data.
        create_plot_widget(self): Creates a plot widget for the plugin.
    """

    def __init__(self):
        super().__init__()
        print("InclinationGamePlugin has been initialized!")

    def start_log_cb(self):
        """Handle the start of logging.

        Parameters:
        - None

        Returns:
        - None
        """
        print("PLUGIN2 start_log_cb method called")

    def stop_log_cb(self):
        """Handle the stop of logging.

        Parameters:
        - None

        Returns:
        - None
        """
        print("PLUGIN2 stop_log_cb method called")

    def tag_cb(self, status, label):
        """Receive a tag event.

        Parameters:
        - status (str | int): Tag status.
        - label (str): Tag label.

        Returns:
        - None
        """
        print("PLUGIN2 tag_cb method called: tag label: ", label, " status: ", status)

    def process(self, data):
        """
        Process the input data and add the mean values of x and y data to the plot widget.

        Parameters:
        - data (HSD_DataToolkit_data): Object with `comp_name` and `data` (numpy arrays).

        Returns:
        - HSD_DataToolkit_data: The same input object, unmodified.
        """
        #print("PLUGIN2 process method called")

        if data.comp_name == "iis3dwb_acc":

            # Get sensor data
            acc_data = data.data

            # Get sensor sensitivity
            self.sensitivity = self.components_status["iis3dwb_acc"]["sensitivity"]

            acc_data = acc_data * self.sensitivity

            # Extract x and y data from the input data
            x_data = acc_data[0]
            y_data = acc_data[1]

            x_filtered_mean = np.mean(x_data)
            y_filtered_mean = np.mean(y_data)

            self.plot_widget.add_data([[x_filtered_mean], [y_filtered_mean]])

        return data

    def create_plot_widget(self):
        """Create the plugin's plot widget.

        Parameters:
        - None

        Returns:
        - PlotScatterWidget: The created scatter plot widget.
        """
        print("PLUGIN2 create_plot_widget method called")
        self.plot_widget = PlotScatterWidget(
            "Plugin2",
            "Plugin2",
            -1,
            1,
            "",
            p_id=0,
            parent=None,
        )
        return self.plot_widget
