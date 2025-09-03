#!/usr/bin/env python
# coding: utf-8 
# *****************************************************************************
#  * @file    stdatalog_API_examples_HSDLink.py
#  * @author  SRA
#  * @version 1.0.0
#  * @date    11-Jul-2024
# *****************************************************************************
#
#                   Copyright (c) 2020 STMicroelectronics.
#                             All rights reserved
#
#   This software component is licensed by ST under BSD-3-Clause license,
#   the "License"; You may not use this file except in compliance with the
#   License. You may obtain a copy of the License at:
#                        https://opensource.org/licenses/BSD-3-Clause


import sys
import os
from threading import Thread
import struct

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
from threading import Event
from stdatalog_core.HSD_link.HSDLink import HSDLink, SensorAcquisitionThread
from stdatalog_pnpl.PnPLCmd import PnPLCMDManager
from stdatalog_core.HSD_utils.DataReader import DataReader
from stdatalog_core.HSD_utils.DataClass import DataClass
from stdatalog_core.HSD.utils.type_conversion import TypeConversion
from datetime import datetime

class ReadSerialDataThread(Thread):
    def __init__(self, hsd_link):
        Thread.__init__(self)
        self.hsd_link = hsd_link
        self.name = "data_reader_thread"
        self.stop_event = Event()
        self.data_reader_params = None
        self.sig_streaming_error = None
        self.prev_cnts = []

    def set_data_reader_params(self, data_reader_params):
        self.data_reader_params = data_reader_params
        self.prev_cnts = [0]*len(data_reader_params)
    
    def set_sig_streaming_error(self, sig_streaming_error):
        self.sig_streaming_error = sig_streaming_error

    def run(self):
        while not self.stop_event.is_set():
            pkt = self.hsd_link.get_serial_data()
            if pkt:
                data = pkt.data
                if pkt.header.cr == 0 and len(data) > 0:
                    curr_cnt = struct.unpack("=i", data[0:4])[0]
                    data_ch = pkt.header.ch_num
                    diff = curr_cnt - self.prev_cnts[data_ch]
                    payload_len = len(data)-4
                    if curr_cnt != 0 and diff != payload_len:
                        log.error("Streaming error occoured!")
                    else:
                        comp_name = self.data_reader_params[data_ch].get("comp_name")
                        self.data_reader_params[data_ch].get("data_reader").feed_data(DataClass(comp_name, data[4:]))
                        file = self.data_reader_params[data_ch].get("file")
                        if not file.closed:
                            file.write(data)
                    self.prev_cnts[data_ch] = curr_cnt

        # self.hsd_link.flush()
        # time.sleep(1)
        self.data_reader_params[0].get("file").close()

    def stop(self):
        self.stop_event.set()

def dummy_function(data):
    pass
    

def main():
    """
    This is the main function that demonstrates the usage of the HSDLink API.
    NOTE: It is necessary to connect a compatible device to the PC to run the script.

    It performs various operations such as retrieving device information, setting sensor parameters,
    uploading UCF files, and updating device configuration.

    Note: Update the file paths for UCF files and device configuration as per your setup.
            Update also the sensor names, sensor parameters and the acquisition duration as per your requirements.

    """
    
    # Create an instance of HSDLink
    hsd_link = HSDLink()

    # Create the appropriate HSDLink instance based on the connected board
    hsd_link_instance = hsd_link.create_hsd_link(dev_com_type='st_serial_datalog')

    if hsd_link is None:
        print("No compatible devices connected.")
        return

    # Get the list of connected devices
    devices = hsd_link.get_devices(hsd_link_instance)
    print(f"Connected Devices: {devices}")

    if not devices:
        print("No devices found.")
        return
    
    # Use the first connected device for demonstration
    device_id = 0

    is_open = hsd_link_instance.open("COM30", 1843200)

    # If hsd_link being used is a serial link, start a thread to read data from the serial port
    #serial_thread_stop_flag = Event()
    serial_thread = ReadSerialDataThread(hsd_link_instance)

    serial_thread.start()

    # Get Device Presentation String
    device_presentation = hsd_link.get_device_presentation_string(hsd_link_instance, device_id)
    print(f"Device Presentation: {device_presentation}")

    # Get device information
    device_info = hsd_link.get_device_info(hsd_link_instance, device_id)
    print(f"Device Info: {device_info}")

    # Get acquisition information
    acquisition_info = hsd_link.get_acquisition_info(hsd_link_instance, device_id)
    print(f"Acquisition Info: {acquisition_info}")

    # Update base acquisition folder
    # [UNCOMMENT] The following lines to update the base acquisition folder and check the result
    # new_base_acquisition_folder = "new_base_acquisition_folder"
    # hsd_link.update_base_acquisition_folder(hsd_link_instance, new_base_acquisition_folder)
    # acquisition_folder_path = hsd_link.get_acquisition_folder(hsd_link_instance)
    # print(f"Updated Acquisition Folder: {acquisition_folder_path}")

    # Get firmware information
    firmware_info = hsd_link.get_firmware_info(hsd_link_instance, device_id)
    print(f"Firmware Info: {firmware_info}")

    # message = PnPLCMDManager.create_command_cmd("log_controller","set_dfu_mode")
    # print(hsd_link.send_command(hsd_link_instance, device_id, message))

    # Set acquisition name
    hsd_link.set_acquisition_name(hsd_link_instance, device_id, "New Name")
    # Set acquisition description
    hsd_link.set_acquisition_description(hsd_link_instance, device_id, "New Description")
    acquisition_info = hsd_link.get_acquisition_info(hsd_link_instance, device_id)
    print(f"Updated Acquisition Info: {acquisition_info}")
    # Set acquisition information
    hsd_link.set_acquisition_info(hsd_link_instance, device_id, "New Acquisition", "Description of the acquisition")
    acquisition_info = hsd_link.get_acquisition_info(hsd_link_instance, device_id)
    print(f"Updated Acquisition Info: {acquisition_info}")

    # Get sensor list
    sensor_list = hsd_link.get_sensor_list(hsd_link_instance, device_id)
    print(f"Sensor List: {sensor_list}")
    # Get Sensor Components number
    sensor_counts = hsd_link.get_sensors_count(hsd_link_instance, device_id)
    print(f"Sensor Counts: {sensor_counts}")
    # Get Sensor Components names list
    sensor_names = hsd_link.get_sensors_names(hsd_link_instance, device_id)
    print(f"Sensor Names: {sensor_names}")
    print(hsd_link.get_sensors_names(hsd_link_instance, device_id))

    if not sensor_list:
        print("No sensors found.")
        return

    # Use the first sensor names for demonstration
    comp_name = sensor_names[0]
    
    # Get Component Status
    comp_status = hsd_link.get_component_status(hsd_link_instance, device_id, comp_name)
    print(f"Component Status: {comp_status}")

    # Get configuration of the first sensor and setup the DataReader
    spts = comp_status[comp_name].get("samples_per_ts", 0)
    dim = comp_status[comp_name].get("dim", 0)
    data_type = comp_status[comp_name].get("data_type", "int16")
    sample_size = TypeConversion.check_type_length(data_type)
    data_format = TypeConversion.get_format_char(data_type)
    
    sensitivity = comp_status[comp_name].get("sensitivity", 1)

    data_reader_params = {}
    dr = DataReader(dummy_function, comp_name, spts, dim, sample_size, data_format, sensitivity)
 
    # Create a new directory with the current date and time
    dir_name = datetime.now().strftime("%Y%m%d_%H_%M_%S")
    dir_path = os.path.join(os.getcwd(), dir_name)
    os.makedirs(dir_path, exist_ok=True)

    print(f"Data will be saved in: {dir_path}")

    file_name = dir_path + "/" + comp_name + ".dat"
    file = open(file_name, "wb+")
    
    data_reader_params[0] = {
        "comp_name":comp_name,
        "data_reader":dr,
        "file":file
    }

    # Set the data reader parameters for the serial thread
    serial_thread.set_data_reader_params(data_reader_params)

    # Use the first sensor for demonstration
    sensor_name, _ = next(iter(sensor_list.items()))
    # Get sensor enabled status
    sensor_enabled = hsd_link.get_sensor_enabled(hsd_link_instance, device_id, sensor_name=sensor_name)
    print(f"Sensor Enabled: {sensor_enabled}")

    # Set sensor enabled status (True in this example)
    hsd_link.set_sensor_enable(hsd_link_instance, device_id, True, sensor_name=sensor_name)

    # # Get sensor ODR Enum id. (The correspondent value can be obtained from the odr Enum property defined in the Device Template Model)
    # sensor_odr = hsd_link.get_sensor_odr(hsd_link_instance, device_id, sensor_name=sensor_name)
    # print(f"Sensor ODR: {sensor_odr}")

    # # Set sensor ODR Enum id. (The correspondent value can be obtained from the odr Enum property defined in the Device Template Model)
    # hsd_link.set_sensor_odr(hsd_link_instance, device_id, 6, sensor_name=sensor_name)

    # # Get sensor FS. (The correspondent value can be obtained from the odr Enum property defined in the Device Template Model)
    # sensor_fs = hsd_link.get_sensor_fs(hsd_link_instance, device_id, sensor_name=sensor_name)
    # print(f"Sensor FS: {sensor_fs}")

    # # Set sensor ODR (The correspondent value can be obtained from the odr Enum property defined in the Device Template Model)
    # hsd_link.set_sensor_fs(hsd_link_instance, device_id, 2, sensor_name=sensor_name)

    # Set RTC time on the device
    hsd_link.set_RTC(hsd_link_instance, device_id)

    # Get the first sensor name. Change the index to get another sensor
    sensor_names = hsd_link.get_sensors_names(hsd_link_instance, device_id)

    # Start data log progress. The log will be stopped after 12 seconds in this example
    # The log will be saved in the acquisition folder and the device_config.json and acq_info.json
    # files will be saved in the same folder. The device_config.json and acq_info.json files can be 
    # saved in a different folder by providing the path as an argument
    print(hsd_link_instance.start_log(device_id, acq_folder=dir_path, sub_folder=False))

    # The acquisition duration is set to 12 seconds in this example. You can change it as per your requirements
    acquisition_time = 12
    for i in range(acquisition_time):
        print(f"Waiting for {acquisition_time-i} seconds before stopping the log...")
        time.sleep(1)
        # The following line is used to check if the PnPL messages are managed correctly by the FW when data streaming is active
        # sensor_names = hsd_link.get_sensors_names(hsd_link_instance, device_id)
        

    # Stop data log process
    print(hsd_link.stop_log(hsd_link_instance, device_id))

    # Save JSON device file
    hsd_link.save_json_device_file(hsd_link_instance, device_id, dir_path)
    # [UNCOMMENT] the following line and replace the "path/to/device_config.json" string with a valid path to save the device_config.json file in that path
    # hsd_link.save_json_device_file(hsd_link_instance, device_id, "path/to/save/device_config.json")
    
    # Save JSON acquisition info file
    hsd_link.save_json_acq_info_file(hsd_link_instance, device_id, dir_path)
    # [UNCOMMENT] the following line and replace the "path/to/acquisition_info.json" string with a valid path to save the acquisition_info.json file in that path
    # hsd_link.save_json_acq_info_file(hsd_link_instance, device_id, "path/to/save/acquisition_info.json")

    serial_thread.stop()
    hsd_link_instance.close()

    print("\n---> End of Serial APIs test script.")

if __name__ == "__main__":
    main()
