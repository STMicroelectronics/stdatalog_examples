#!/usr/bin/env python
# coding: utf-8 
# *****************************************************************************
#  * @file    stdatalog_data_export_by_tags.py
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
#

"""
This script, `stdatalog_data_export_by_tags.py`, is designed to export data from acquisition folders
generated by STMicroelectronics' HSDatalog tool. It supports various options for customizing
the data export, including selecting specific sensors, setting time ranges, exporting raw data,
including annotations, and more.
It uses Click for command-line interface options and logs information and errors during execution.
The script can be run from the command line with various options to tailor the data export
to the user's needs.

NOTEs:
- The input acquisition folder must be labeled (check the tags field in acquisition_info.json file).
- Exported files will be saved in the specified output folder and organized as follows:
    - One folder for each tag class label containing the exported data files for the corresponding sensors.
    - In each tag class folder, a set of files for each sensor will be saved. The number of files for each
        sensor depends on the number of tag groups in sensor data. Each file will contain data of a specific tag group.
        (A tag group is a set of consecutive samples in which the tag label is active (True in the dataframe)).
    Example:
    - SW_TAG_0:
        - SW_TAG_0_iis3dwb_acc_dataLog_0.csv //SW_TAG_0, Tag group 0
        - SW_TAG_0_iis3dwb_acc_dataLog_1.csv //SW_TAG_0, Tag group 1
        - ...
        - SW_TAG_0_stts22h_temp_dataLog_0.csv //SW_TAG_0, Tag group 0
        - SW_TAG_0_stts22h_temp_dataLog_1.csv //SW_TAG_0, Tag group 1
    - SW_TAG_N:
        - SW_TAG_N_iis3dwb_acc_dataLog_0.csv //SW_TAG_N, Tag group 0
        - SW_TAG_N_iis3dwb_acc_dataLog_1.csv //SW_TAG_N, Tag group 1
        - ...
        - SW_TAG_N_stts22h_temp_dataLog_0.csv //SW_TAG_N, Tag group 0
        - SW_TAG_N_stts22h_temp_dataLog_1.csv //SW_TAG_N, Tag group 1

Key Features:
- Export data for specific sensors or all active components.
- Set start and end times for the data export.
- Option to export raw data.
- Include annotations in the exported data.
- Filter data by tag labels.
- Include data sections without tags in the exported output.
- Specify the size of each data chunk to be processed.
- Export data in different formats (TXT, CSV, TSV).
- Upload and use a custom Device Template Model (DTDL).
- Enable debug mode to check for corrupted data and timestamps.
- Export data by tags, organizing exported files (one per selected sensor) in different files and folders based on tag labels groups.
- Option to save a folder containing all untagged data.
"""

import sys
import os

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..\\..')))

import click
from stdatalog_core.HSD_utils.dtm import HSDatalogDTM
from stdatalog_core.HSD_utils.exceptions import MissingDeviceModelError, MissingTagsException, MissingISPUOutputDescriptorException
import stdatalog_core.HSD_utils.logger as logger
from stdatalog_core.HSD.HSDatalog import HSDatalog

# Set up the application logger
log = logger.setup_applevel_logger(is_debug = False, file_name= "app_debug.log")

# Define the script version
script_version = "1.0.0"

# Define a callback function to show help information
def show_help(ctx, param, value):
    if value and not ctx.resilient_parsing:
        # Display the help information for the command
        click.secho(ctx.get_help(), color=ctx.color)
        # Display examples of script execution
        click.secho("\n-> Script execution examples:")
        #This command will extract data for all active sensors from the specified acquisition folder.
        click.secho("   python stdatalog_data_export_by_tags.py Acquisition_Folder_Path -s all", fg='cyan')
        #This command will extract data for all active sensors, remove the timestamps column, export the data in CSV format and save it to the specified output folder.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -nt -f CSV -s all -o Output_Folder_Path", fg='cyan')
        #This command will extract data for a specific sensor named SENSOR_NAME and save it to the specified output folder.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -o Output_Folder_Path -s SENSOR_NAME", fg='cyan')
        #This command will extract data for the sensor SENSOR_NAME, starting from 3 seconds and ending at 6 seconds.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -st 3 -et 6 -s SENSOR_NAME", fg='cyan')
        #This command will extract data for all active sensors, but only include entries that have the tag labels SW_TAG_0 or SW_TAG_2.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -tl SW_TAG_0 -tl SW_TAG_2 -s all", fg='cyan')
        #This command will extract data for the sensor SENSOR_NAME and include data sections without tags in the exported output files.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -wu -s SENSOR_NAME", fg='cyan')
        #This command will extract raw data (not multiplied by sensitivity) for the sensor SENSOR_NAME.        
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -r -s SENSOR_NAME", fg='cyan')
        #This command will upload a custom Device Template Model (DTDL) "custom_model.json" with board_id=0xff, fw_id=0xff and extract data for the sensor SENSOR_NAME.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -cdm 255 255 custom_model.json -s SENSOR_NAME", fg='cyan')
        #This command will specify the size of each data chunk to be 1000 samples for the sensor SENSOR_NAME.
        click.secho("   python stdatalog_data_export_by_tags.py path_to_acquisition_folder -cs 1000 -s SENSOR_NAME", fg='cyan')
        # Exit the context after showing help
        ctx.exit()

# Define the click command with options for the data export script
@click.command()
@click.argument('acq_folder', type=click.Path(exists=True))
@click.option('-o', '--output_folder', help="Output folder (this will be created if it doesn't exist)")
@click.option('-s', '--sensor_name', help="Sensor Name - use \"all\" to extract all active sensors data, otherwise select a specific sensor by name", default='')
@click.option('-st','--start_time', help="Start Time - Data conversion will start from this time (seconds)", type=int, default=0)
@click.option('-et','--end_time', help="End Time - Data conversion will end up in this time (seconds)", type=int, default=-1)
@click.option('-tl', '--tag_labels', multiple=True, help='A list of tag labels strings to filter and include only the corresponding entries in the converted output')
@click.option('-wu', '--with_untagged', help="Enable this option to include data sections without tags in the exported output files. A dedicated \"untagged\" folder will be created", is_flag=True, default=False)
@click.option('-nt','--no_timestamps', help="Enable this option to remove timestamps column in the exported output files", is_flag=True, default=False)
@click.option('-f', '--out_format', help="Select exported data format", type=click.Choice(['TXT', 'CSV', 'TSV'], case_sensitive=False))
@click.option('-r', '--raw_data', is_flag=True, help="Uses Raw data (not multiplied by sensitivity)", default=False)
@click.option('-cdm','--custom_device_model', help="Upload a custom Device Template Model (DTDL). board_id:int, fw_id:int, device_template_model json path:str", type=(int, int, str))
@click.option('-cs', '--chunk_size', help="Specify the size (number of samples) of each data chunk to be processed", default=HSDatalog.DEFAULT_SAMPLES_CHUNK_SIZE)
@click.version_option(script_version, '-v', '--version', prog_name="stdatalog_data_export_by_tags", is_flag=True, help="stdatalog_data_export_by_tags converter script version number")
@click.option('-d', '--debug', is_flag=True, help="[DEBUG] Check for corrupted data and timestamps", default=False)
@click.option("-h", "--help", is_flag=True, is_eager=True, expose_value=False, callback=show_help, help="Show this message and exit.",)

# Define the main function that will be executed when the script is run
def hsd_exportByTags(acq_folder, output_folder, sensor_name, start_time, end_time, tag_labels, with_untagged, no_timestamps, raw_data, out_format, custom_device_model, chunk_size, debug):

    # If a custom device model is provided, upload it
    if custom_device_model is not None:
        HSDatalogDTM.upload_custom_dtm(custom_device_model)

    # Create an instance of the HSDatalog factory
    hsd_factory = HSDatalog()
    try:
        # Create an HSDatalog object for the given acquisition folder
        hsd = hsd_factory.create_hsd(acq_folder)
    except MissingDeviceModelError as error:
        # Handle the case where the device model is missing
        log.error("Device Template Model identifyed by [{}] not supported".format(error))
        log.info("Check your input acquisition folder, then try to upload a custom Device Template Model using -cdm flag".format(error))
        return

    # Set the default output format if not specified
    if out_format is None:
        out_format = "CSV"

    # Process tag labels if provided as selection filter
    which_tags = []
    if len(tag_labels) > 0:
        which_tags = list(tag_labels)

    # Set the default output folder if not specified
    output_folder = acq_folder + "_Exported" if output_folder is None else output_folder
    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    # Enable timestamp recovery if debug mode is on
    hsd.enable_timestamp_recovery(debug)
    
    # Main loop to process data export by tags
    df_flag = True
    while df_flag:
        # If no sensor name is provided, ask the user to select a component
        if sensor_name == '':
            component = HSDatalog.ask_for_component(hsd, only_active=True)
            # If a component is selected, convert its data
            if component is not None:
                convert_data(hsd, component, start_time, end_time, output_folder, out_format, which_tags, with_untagged, no_timestamps, raw_data, chunk_size)
            else:
                break
        # If 'all' is specified for sensor name, process all active components
        elif sensor_name == 'all':
            component_list = HSDatalog.get_all_components(hsd, only_active=True)
            for component in component_list:
                convert_data(hsd, component, start_time, end_time, output_folder, out_format, which_tags, with_untagged, no_timestamps, raw_data, chunk_size)
            # Set flag to False to exit the loop after processing all components
            df_flag = False
        # If a specific sensor name is provided, process only that component
        else:
            component = HSDatalog.get_component(hsd, sensor_name)
            if component is not None:
                convert_data(hsd, component, start_time, end_time, output_folder, out_format, which_tags, with_untagged, no_timestamps, raw_data, chunk_size)
            else:
                # Log an error if the specified component is not found
                log.error("No \"{}\" Component found in your Device Configuration file.".format(sensor_name))
            # Set flag to False to exit the loop after processing the specified component
            df_flag = False

# Define a helper function to convert data
def convert_data(hsd, component, start_time, end_time, output_folder, out_format, which_tags:list, with_untagged, no_timestamps, raw_data, chunk_size):
    try:
        # Attempt to convert data to text by tags
        HSDatalog.convert_dat_to_txt_by_tags(hsd, component, start_time, end_time, output_folder, out_format, which_tags, with_untagged, no_timestamps, raw_data, chunk_size)
    except MissingTagsException as tags_err:
        # Handle missing tags exception
        log.error(tags_err)
        log.warning("Check \"tags\" field in your acquisition_info.json file (AcquisitionInfo.json for HSDv1 acquisitions)")
        quit()
    except MissingISPUOutputDescriptorException as ispu_err:
        # Handle missing ISPU output descriptor exception
        log.error(ispu_err)
        log.warning("Copy the right ISPU output descriptor file in your \"{}\" acquisition folder renamed as \"ispu_output_format.json\"".format(hsd.get_acquisition_path()))
    except Exception as err:
        log.exception(err)

if __name__ == '__main__':
    # Execute the main function
    hsd_exportByTags()

