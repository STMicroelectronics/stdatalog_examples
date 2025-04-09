from multiprocessing import Event
import sys
import os

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../..')))

import csv

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices
from PySide6.QtCore import QUrl

import numpy as np
from stdatalog_core.HSD.HSDatalog import HSDatalog
import stdatalog_core.HSD_utils.logger as logger

# Set up the application logger to record debug information and errors
log = logger.setup_applevel_logger(is_debug = False, file_name= "app_debug.log")

DECIMATION = 4

class DatasetCreationWorker(QThread):
    success = Signal()
    error = Signal(str)
    message = Signal(str)


    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            MC_AI_dataset_creation(self.folder_path, self.message)
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))


def MC_AI_dataset_creation(main_folder, message_signal):
    if not os.path.isdir(main_folder):
        print("The provided path is not a directory.")
        return

    class_file_paths = []

    # Create an instance of HSDatalog
    hsd = HSDatalog()

    # Validate the HSD folder and determine the version
    hsd_version = hsd.validate_hsd_folder(main_folder)
    print(f"HSD Version: {hsd_version}\n")

    # Create the appropriate HSDatalog instance based on the folder content
    hsd_instance = hsd.create_hsd(acquisition_folder=main_folder)

    # Define the output folder within the main folder
    output_folder = os.path.join(main_folder, "output")

    # Create the output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    acc_dat = hsd.get_data_and_timestamps_by_name(hsd_instance, "iis3dwb_acc", start_time=0, end_time=-1, raw_data = True)
    fmc_dat = hsd.get_data_and_timestamps_by_name(hsd_instance, "fast_mc_telemetries", start_time=0, end_time=-1, raw_data = True)
    
    # Concatenate the accelerometer data chunck in a single array @acc_data
    chunck_acc_data = [chunck_acc_data[0] for chunck_acc_data in acc_dat]
    acc_data = np.concatenate(chunck_acc_data)

    # Concatenate the accelerometer timestamp chunck in a single array @acc_timestamp
    chunck_acc_ts = [chunck_acc_ts[1] for chunck_acc_ts in acc_dat]
    acc_timestamp = np.concatenate(chunck_acc_ts)

    # Get I_q data and timestamp
    fmc_data = fmc_dat[0][0]
    fmc_timestamp = fmc_dat[0][1]

    # Get tags
    tags = hsd.get_time_tags(hsd_instance)

    # Extract tag labels
    for tag in tags:# Multiple tag groups are not supported by this script
        start_time = tag['time_start']
        end_time = tag['time_end']
        label = tag['label']
        
        # Find the index of the nearest timestamp for fmc_timestamp and acc_timestamp based on start_time
        fmc_start_index = (np.abs(fmc_timestamp - start_time)).argmin()
        acc_start_index = (np.abs(acc_timestamp - start_time)).argmin()
        # Find the index of the nearest timestamp for fmc_timestamp and acc_timestamp based on end_time
        fmc_end_index = (np.abs(fmc_timestamp - end_time)).argmin()
        acc_end_index = (np.abs(acc_timestamp - end_time)).argmin()
        # Trim the data based on the start and end indices
        
        fmc_data_trimmed = fmc_data[fmc_start_index:fmc_end_index]
        fmc_time_trimmed = fmc_timestamp[fmc_start_index:fmc_end_index]
        acc_data_trimmed = acc_data[acc_start_index:acc_end_index]
        acc_time_trimmed = acc_timestamp[acc_start_index:acc_end_index]

        # Create tag folder
        tag_folder = os.path.join(output_folder, label)
        if not os.path.exists(tag_folder):
            os.makedirs(tag_folder)

        cf_path = os.path.join(tag_folder, f"{label}.csv")
        class_file_paths.append(cf_path)

        # Create datasets from the trimmed data
        dataset_creation(fmc_data_trimmed, fmc_time_trimmed, acc_data_trimmed, acc_time_trimmed, cf_path, message_signal)

        fmc_timestamp = fmc_timestamp[fmc_end_index::]
        fmc_data = fmc_data[fmc_end_index::]
        acc_timestamp = acc_timestamp[acc_end_index::]
        acc_data = acc_data[acc_end_index::]

    # After generating all files, correct the length of all class_file_path CSVs
    if class_file_paths:
        truncate_csv_files_to_min_length(class_file_paths)
    
    # Open the output folder
    QDesktopServices.openUrl(QUrl.fromLocalFile(output_folder))
    log.info(f"Dataset creation completed successfully.")

def extract_n_elements_before_indices(values, indices, n):
    # initialize an empty list to store the results
    result = []

    # loop over each index in the array
    for i in indices:
        # extract n elements before the index
        start_index = i - n
        end_index = i
        if start_index < 0:
            start_index = 0
        extracted_values = values[start_index:end_index]
        # add the extracted values to the result list
        result.append(extracted_values)

    return result

def find_closest_minor_indices(values, candidates):
    # sort candidate array in ascending order
    candidates_sorted = np.sort(candidates)

    # initialize an array to store the indices of the closest minor values
    indices = np.zeros_like(values, dtype=int)

    # loop over each element in values
    for i, v in enumerate(values):
        # find the index of the closest minor value in candidates
        index = np.searchsorted(candidates_sorted, v, side='left') - 1
        # handle edge cases where v is smaller than the smallest value in candidates
        if index < 0:
            index = 0
        # store the index in the result array
        indices[i] = index

    return indices

def csv_to_array(file_path):
    # load the CSV file into a NumPy array, skipping the first row
    array = np.loadtxt(file_path, delimiter=',', skiprows=1, dtype=np.float32)

    return array

def array_decimation(array, decimation, axis):
    # reshape the input array into a 3D array
    array_3d = np.reshape(array, (axis, -1, decimation))

    # compute the average of every decimation samples along the second dimension
    decimated_array = np.mean(array_3d, axis=1)

    # flatten the decimated array and return it
    return decimated_array.flatten()

def decimate_1d_array_by_average(arr, decimation):
    """
    Decimates a 1D NumPy array by computing the average of every `decimation` elements.
    
    Args:
    arr (numpy.ndarray): The input array to be decimated.
    decimation (int): The factor by which to decimate the array.
    
    Returns:
    numpy.ndarray: The decimated array.
    """
    return np.mean(arr.reshape(-1, decimation), axis=1)

def decimate_2d_array_by_average(arr, decimation):
    """
    Decimates a 2D NumPy array along the first axis by computing the average of every `decimation` rows.
    
    Args:
    arr (numpy.ndarray): The input array to be decimated.
    decimation (int): The factor by which to decimate the arrays.
    
    Returns:
    numpy.ndarray: The decimated array.
    """
    return np.mean(arr.reshape(-1, decimation, arr.shape[1]), axis=1)

def decimate_array_by_average(arr, decimation):
    """
    Decimates a 1D or 2D NumPy array along the first axis by computing the average of every `decimation` rows or elements.
    
    Args:
    arr (numpy.ndarray): The input array to be decimated.
    decimation (int): The factor by which to decimate the array.
    
    Returns:
    numpy.ndarray: The decimated array.
    """
    if arr.ndim == 1:
        return decimate_1d_array_by_average(arr, decimation)
    elif arr.ndim == 2:
        return decimate_2d_array_by_average(arr, decimation)
    else:
        raise ValueError("Input array must be 1D or 2D")

def decimate_array_list_by_average(arr_list, decimation):
    """
    Decimates a list of 2D NumPy arrays along the first axis by computing the average of every `decimation` rows.
    
    Args:
    arr_list (list): The list of input arrays to be decimated.
    decimation (int): The factor by which to decimate the arrays.
    
    Returns:
    list: The list of decimated arrays.
    """
    return [decimate_array_by_average(arr, decimation) for arr in arr_list]

def concatenate_lists(arr_list1, arr_list2):
    # Check that the two lists have the same length
    if len(arr_list1) != len(arr_list2):
        raise ValueError("The two lists must have the same length.")
    
    # Concatenate each array in the two lists along the second axis
    concatenated_list = [np.concatenate((arr1, arr2), axis=1) 
                        for arr1, arr2 in zip(arr_list1, arr_list2)]
    return concatenated_list

def flatten_arrays(arr_list):
    # Reshape each array in the list to a 1D array
    flattened_list = [arr.reshape(-1) for arr in arr_list]
    
    return flattened_list

def dataset_creation(fast_telemetry_data, fast_telemetry_ts, iis3dwb_acc_data, iis3dwb_acc_ts, output_data_set_file_path, message_signal):
    # Flatten the timestamps
    fast_telemetry_ts = fast_telemetry_ts.flatten()
    iis3dwb_acc_ts = iis3dwb_acc_ts.flatten()
    #extract timestamp each fast_telemetry packet dimension x decimation
    fast_telemetry_decimated_ts = fast_telemetry_ts[1024*DECIMATION::1024*DECIMATION]
    iis3dwb_acc_decimated_idx = find_closest_minor_indices(fast_telemetry_decimated_ts, iis3dwb_acc_ts.flatten())
    fast_telemetry_decimated_idx = np.arange(1024*DECIMATION, len(fast_telemetry_data), 1024*DECIMATION)

    fast_telemetry_data_decimated_in =  extract_n_elements_before_indices(fast_telemetry_data, fast_telemetry_decimated_idx, 1024*DECIMATION)
    iis3dwb_acc_decimated_in = extract_n_elements_before_indices(iis3dwb_acc_data, iis3dwb_acc_decimated_idx, 1024*DECIMATION)

    fast_telemetry_data_decimated_out = decimate_array_list_by_average(fast_telemetry_data_decimated_in,DECIMATION)
    iis3dwb_acc_decimated_out = decimate_array_list_by_average(iis3dwb_acc_decimated_in,DECIMATION)

    aggregated_data = concatenate_lists(iis3dwb_acc_decimated_out, fast_telemetry_data_decimated_out)

    aggregated_data_flatten = flatten_arrays(aggregated_data)
    
    # Open the output file in append mode
    with open(output_data_set_file_path, 'w',  newline='') as output_file:

        # Create a CSV writer for the output file
        writer = csv.writer(output_file)

        # Write the aggregated data to the output file
        for row in aggregated_data_flatten:
            writer.writerow(row)

    message_signal.emit(f"{output_data_set_file_path} CREATED")

def truncate_csv_files_to_min_length(csv_file_paths):
    # Determine the minimum length among the CSV files
    min_length = float('inf')
    for file_path in csv_file_paths:
        data = np.genfromtxt(file_path, delimiter=',', skip_header=1)  # Assuming there's a header
        min_length = min(min_length, data.shape[0])

    # Truncate each CSV file to the minimum length
    for file_path in csv_file_paths:
        # Load the data
        with open(file_path, 'r') as f:
            header = f.readline()  # Read the header line
            data = np.genfromtxt(f, delimiter=',', skip_header=0)  # Already skipped the header

        # Truncate the data
        truncated_data = data[:min_length]

        # Write the truncated data back to the CSV file
        with open(file_path, 'w') as f:
            f.write(header)  # Write the header line
            np.savetxt(f, truncated_data, delimiter=',', fmt='%g')  # Use '%g' for floating-point format

class DragDropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Drag and Drop the datalogMC acquisation here")
        self.setStyleSheet("QLabel { background-color : #2E2E2E; color : white; font-size: 16px; }")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            folder_path = urls[0].toLocalFile()
            if os.path.isdir(folder_path):
                self.start_thread(folder_path)
            else:
                QMessageBox.critical(None, "Error", "Please drop a valid folder.")

    def start_thread(self, folder_path):
        self.update_label("Dataset creation in progress. The task will take some minutes.")
        self.thread = DatasetCreationWorker(folder_path)
        self.thread.success.connect(self.on_success)
        self.thread.error.connect(self.on_error)
        self.thread.message.connect(self.update_label)
        self.thread.finished.connect(self.reset_label)
        self.thread.start()

    def update_label(self, text):
        self.setText(text)

    def reset_label(self):
        self.setText("Drag and Drop the datalogMC acquisation here")

    def on_success(self):
        QMessageBox.information(None, "Success", "Dataset creation completed successfully.")

    def on_error(self, error_message):
        QMessageBox.critical(None, "Error", f"An error occurred: {error_message}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC AI Dataset Creation")
        self.setFixedSize(1200, 200)  # Set fixed size for the window
        self.setStyleSheet("background-color: #2E2E2E;")

        layout = QVBoxLayout()
        self.label = DragDropLabel(self)
        layout.addWidget(self.label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
