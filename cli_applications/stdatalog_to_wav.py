#!/usr/bin/env python
# coding: utf-8 
# *****************************************************************************
#  * @file    stdatalog_to_wav.py
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
This script, `stdatalog_to_wav.py`, is designed to convert data from acquisition folders
generated by STMicroelectronics' HSDatalog tool into WAV format.
It supports various options for customizing the data conversion, including selecting specific sensors,
setting time ranges, specifying output folder, and more.
It uses Click for command-line interface options and logs information and errors during execution.
The script can be run from the command line with various options to tailor the data conversion
to the user's needs.

Key Features:
- Convert data for specific sensors or all active components.
- Set start and end times for the data conversion.
- Specify the output folder.
- Split the output into separate files for each tag.
- Upload and use a custom Device Template Model (DTDL).
- Specify the size of each data chunk to be processed.
"""

import sys
import os

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import click
from stdatalog_core.HSD_utils.dtm import HSDatalogDTM
from stdatalog_core.HSD_utils.exceptions import MissingDeviceModelError
import stdatalog_core.HSD_utils.logger as logger
from stdatalog_core.HSD.HSDatalog import HSDatalog

# Set up the application logger to record debug information and errors
log = logger.setup_applevel_logger(is_debug = False, file_name= "app_debug.log")

# Define the script version for reference
script_version = "1.0.0"

# Define a callback function to show help information and example usage of the script
def show_help(ctx, param, value):
    if value and not ctx.resilient_parsing:
        # Display the help information for the command
        click.secho(ctx.get_help(), color=ctx.color)
        # Display examples of script execution
        click.secho("\n-> Script execution examples:")
        # Example: Convert data to WAV format for a specific acquisition folder
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path", fg='cyan')
        # Example: Convert data to WAV format for a specific sensor and save in a specified output folder
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path -o Output_Folder_Path -s SENSOR_NAME -st START_TIME -et END_TIME", fg='cyan')
        # Example: Convert data to WAV format for all sensors and split the output by tags
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path -s all -spt", fg='cyan')
        # Example: Convert data to WAV format for a specific sensor with a custom device model
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path -s SENSOR_NAME -cdm BOARD_ID FW_ID custom_model.json", fg='cyan')
        # Example: Convert data to WAV format with a specified chunk size
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path -s SENSOR_NAME -cs 500000", fg='cyan')
        # Example: Convert data to WAV format for a specific time range
        click.secho("   python stdatalog_to_wav.py Acquisition_Folder_Path -s SENSOR_NAME -st 3 -et 6", fg='cyan')
        # Exit the context after showing help
        ctx.exit()

# Define the Click command with options and arguments
@click.command()
@click.argument('acq_folder', type=click.Path(exists=True))
@click.option('-o', '--output_folder', help="Output folder (this will be created if it doesn't exist)")
@click.option('-s', '--sensor_name', help="Sensor Name - use \"all\" to convert all active sensors data, otherwise select a specific sensor by name", default='')
@click.option('-st','--start_time', help="Start Time - Data conversion will start from this time (seconds)", type=int, default=0)
@click.option('-et','--end_time', help="End Time - Data conversion will end up in this time (seconds)", type=int, default=-1)
@click.option('-spt', '--split_per_tags', is_flag=True, help="Enable this option to split the output into separate files for each tag", default=False)
@click.option('-cdm','--custom_device_model', help="Upload a custom Device Template Model (DTDL)", type=(int, int, str))
@click.option('-cs', '--chunk_size', help="Specify the size (number of samples) of each data chunk to be processed", default=10000000)
@click.version_option(script_version, '-v', '--version', prog_name="stdatalog_to_wav", is_flag=True, help="stdatalog_to_wav Converter tool version number")
@click.option('-h', '--help', is_flag=True, is_eager=True, expose_value=False, callback=show_help, help="Show this message and exit.",)

# Define the main function that will be executed when the script is run
def hsd_toWav(acq_folder, output_folder, sensor_name, start_time, end_time, split_per_tags, custom_device_model, chunk_size):
    
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

    # Set the default output folder if not specified
    output_folder = acq_folder + "_Exported" if output_folder is None else output_folder    
    # Create the output folder if it does not exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Enable timestamp recovery
    hsd.enable_timestamp_recovery(True)

    # Main loop to process data conversion by sensor
    df_flag = True
    while df_flag:
        # If no sensor name is provided, prompt the user to select a component
        if sensor_name == '':
            # Prompt the user to select a component if no sensor name is provided
            component = HSDatalog.ask_for_component(hsd, only_active=True)
            if component is not None:
                # Convert data to WAV format for the selected component
                HSDatalog.convert_dat_to_wav(hsd, component, start_time, end_time, output_folder, split_per_tags, chunk_size)
            else:
                # Exit the loop if no component is selected
                break
        # If 'all' is specified for sensor name, process all active components
        elif sensor_name == 'all':
            # Retrieve a list of all active components
            component_list = HSDatalog.get_all_components(hsd, only_active=True)
            # Iterate over each component and convert data to WAV format
            for component in component_list:
                HSDatalog.convert_dat_to_wav(hsd, component, start_time, end_time, output_folder, split_per_tags, chunk_size)
            # Set flag to False to exit the loop after processing all components
            df_flag = False
        # If a specific sensor name is provided, process only that component
        else:
            component = HSDatalog.get_component(hsd, sensor_name)
            if component is not None:
                # Convert data to WAV format for the specified component
                HSDatalog.convert_dat_to_wav(hsd, component, start_time, end_time, output_folder, split_per_tags, chunk_size)
            else:
                # Log an error if the specified component is not found
                log.error("No \"{}\" Component found in your Device Configuration file.".format(sensor_name))
            # Set flag to False to exit the loop after processing the specified component
            df_flag = False

if __name__ == '__main__':
    # Execute the main function
    hsd_toWav()

