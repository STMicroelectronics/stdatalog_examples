from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_Plugin

class PluginClass(HSD_Plugin):

    def __init__(self):
        super().__init__()
        print("HelloWorldPlugin has been initialized!")
    
    def process(self, data):
        """
        Processes the incoming data and logs its details.
        This method prints information about the received data, including the component name,
        data content, timestamp, and the status of the component. The component status is retrieved
        from the `components_status` dictionary using the component name as the key.
        Args:
            data: An object containing the following attributes:
                - comp_name (str): The name of the component sending the data.
                - data: The actual data being processed.
                - timestamp: The timestamp associated with the data.
        Returns:
            The same `data` object that was passed as input.
        Note:
            The printed component status will contain a dictionary with all the properties
            and their values for the component identified by `data.comp_name`.
        """
        print("HelloWorldPlugin process method called")
        print(f"---> Received data from: {data.comp_name}")
        print(f"-----> Data: {data.data}")
        print(f"-----> Timestamp: {data.timestamp}")
        print(f"-----> Component Status: {self.components_status[data.comp_name]}")
        return data

    def create_plot_widget(self):
        print("HelloWorldPlugin create_plot_widget method called")