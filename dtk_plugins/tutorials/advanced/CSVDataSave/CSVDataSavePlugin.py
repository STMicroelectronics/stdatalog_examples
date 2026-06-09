# *****************************************************************************
#  * @file    CSVDataSavePlugin.py
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
"""CSV save plugin for Data Toolkit.

Writes incoming component data to CSV files asynchronously using per-component queues and writer
threads. Reconstructs timestamps based on the last timestamp, number of samples, and output data
rate (ODR), and stores data in the format: `Time, Data_axis_0, Data_axis_1, ...`.
"""

import os
import threading
import queue
from datetime import datetime

import numpy as np
import pandas as pd

from stdatalog_dtk.HSD_DataToolkit_Pipeline import HSD_DataToolkit_data, HSD_Plugin

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

class PluginClass(HSD_Plugin):
    """Saves incoming telemetry to CSV per component.

    Sets up per-component queues and background writer threads. Each queue receives batches
    containing reconstructed timestamps and axis data, which are periodically flushed to CSV.
    """

    def __init__(self):
        """Initialize the CSV data save plugin.

        Parameters:
        - None

        Returns:
        - None
        """
        super().__init__()
        print("CSVDataSavePlugin has been initialized!")
        self.output_dir = OUTPUT_DIR
        self.components_files = {}
        self.data_queues = {}
        self.writer_threads = {}

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    # Method to recreate timestamps based on the last timestamp, number of samples,
    # and output data rate (odr)
    def _recreate_timestamps(self, last_timestamp, num_samples, odr):
        """Recreate timestamps for a batch of samples.

        Parameters:
        - last_timestamp (float): Timestamp of the last sample received.
        - num_samples (int): Number of samples in the batch.
        - odr (float): Output data rate (samples per second).

        Returns:
        - list[float]: Reconstructed timestamps in ascending order.
        """
        interval = 1.0 / odr
        timestamps = [
            last_timestamp - (num_samples - 1 - i) * interval for i in range(num_samples)
        ]
        return timestamps

    # Initialize the CSV file with headers
    def _initialize_csv(self, file_name, headers):
        """Create a CSV file and write header columns.

        Parameters:
        - file_name (str): Destination CSV file path.
        - headers (list[str]): Column names to write as header.

        Returns:
        - None
        """
        print("Initializing CSV file")
        df = pd.DataFrame(columns=headers)
        df.to_csv(file_name, mode="w", header=True, index=False)

    # Function to save a batch of data to CSV
    def _save_batch_to_csv(self, data_batch, file_name):
        """Append a batch of rows to a CSV file.

        Parameters:
        - data_batch (list[np.ndarray] | np.ndarray): Batch rows to save.
        - file_name (str): Destination CSV file path.

        Returns:
        - None
        """
        # Ensure data_batch is a 2D array
        data_batch_2d = np.vstack(data_batch)
        df = pd.DataFrame(data_batch_2d)
        df.to_csv(file_name, mode="a", header=False, index=False)

    # Worker function to write data from the queue to the CSV file
    def _writer_worker(self, data_queue, file_name, batch_size):
        """Background worker that flushes queued data to CSV.

        Parameters:
        - data_queue (queue.Queue): Queue of data batches; terminates on `None`.
        - file_name (str): Destination CSV file path.
        - batch_size (int): Number of chunks per flush.

        Returns:
        - None
        """
        batch = []
        while True:
            data_chunk = data_queue.get()
            if data_chunk is None:
                if batch:
                    self._save_batch_to_csv(batch, file_name)
                break
            batch.append(data_chunk)
            if len(batch) >= batch_size:
                self._save_batch_to_csv(batch, file_name)
                batch = []
            data_queue.task_done()

    # Process incoming data and add it to the queue
    def process(self, data: HSD_DataToolkit_data):
        """Process incoming data and enqueue for CSV writing.

        Parameters:
        - data (HSD_DataToolkit_data): Input object with `comp_name`, `timestamp`, and `data`.

        Returns:
        - None
        """
        component_name = data.comp_name
        if component_name not in self.components_status:
            print(f"Component {component_name} not found in components_status")
            return
        odr = self.components_status[component_name].get("odr", 1)
        dim = self.components_status[component_name].get("dim", 1)
        num_samples = len(data.data) // dim
        timestamps = self._recreate_timestamps(data.timestamp, num_samples, odr)
        axis_data = np.array([data.data[j::dim] for j in range(dim)])
        combined_data = np.column_stack((timestamps, axis_data.T))
        self.data_queues[component_name].put(combined_data)

    # Create a plot widget (currently just a placeholder)
    def create_plot_widget(self):
        """Create the plugin's plot widget (not implemented).

        Parameters:
        - None

        Returns:
        - None
        """
        print("CSVDataSavePlugin create_plot_widget method called")

    # Start logging callback, initializes CSV files and writer threads for each
    # component and starts the writer threads
    def start_log_cb(self):
        """Start logging: initialize CSV and launch writer threads per component.

        Parameters:
        - None

        Returns:
        - None
        """
        current_time = datetime.now().strftime("%Y%m%d_%H_%M_%S")
        for component_name, status in self.components_status.items():
            if status.get("enable", False):
                csv_file_path = os.path.join(
                    self.output_dir,
                    f"{component_name}_{current_time}.csv",
                )
                self.components_files[component_name] = csv_file_path
                header = ["Time"]
                header.extend([f"Data_axis_{i}" for i in range(status.get("dim", 1))])
                batch_size = 5  # Number of chunks per batch chosen for responsiveness
                self.data_queues[component_name] = queue.Queue()
                # Initialize the CSV file
                self._initialize_csv(csv_file_path, header)
                writer_thread = threading.Thread(
                    target=self._writer_worker,
                    args=(
                        self.data_queues[component_name],
                        csv_file_path,
                        batch_size,
                    ),
                )
                self.writer_threads[component_name] = writer_thread
                self.writer_threads[component_name].start()

    # Stop logging callback, stops the writer threads for each component and joins
    # them to the main thread
    def stop_log_cb(self):
        """Stop logging: signal and join writer threads.

        Parameters:
        - None

        Returns:
        - None
        """
        for component_name in self.components_files:
            self.data_queues[component_name].put(None)
            self.writer_threads[component_name].join()
