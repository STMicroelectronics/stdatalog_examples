from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin
from stdatalog_gui.Widgets.Plots.PluginPlotWidget import PluginPlotWidget, PluginPlotType
import numpy as np

class PluginClass(HSD_Plugin):

    def __init__(self):
        super().__init__()
        self.sensitivity = None
        print("FilterPlugin has been initialized!")
    
    def process(self, data):
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
        print("FilterPlugin create_plot_widget method called")
        self.plot_widget = PluginPlotWidget.create_plot("FilterPlugin", PluginPlotType.LINE, dimension=1)
        return self.plot_widget