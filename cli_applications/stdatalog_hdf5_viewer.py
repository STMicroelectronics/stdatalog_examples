#!/usr/bin/env python
# coding: utf-8 
# *****************************************************************************
#  * @file    stdatalog_hdf5_viewer.py
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
This script, `stdatalog_hdf5_viewer.py`, is designed to display the contents of an HDF5 file using the HDF5 Viewer.
The script needs the `hdf5view` package to be installed to display the contents of the HDF5 file. If the package is 
not installed, the script will attempt to install it using pip.
It uses `click` for command-line interface options and logs information and errors during execution.

Key Features:
- Display the contents of an HDF5 file using the HDF5 Viewer.

For a detailed description of how to use the hdf5view package, please refer to the package documentation.

If you are a VSCode user, you can install the `HDF5 Viewer` extension to view the contents of an HDF5 file directly in the editor.
For an online HDF5 file viewing service with more features, please refer to https://myhdf5.hdfgroup.org/
"""

import sys
import os

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..\\..')))

import click
import subprocess

import stdatalog_core.HSD_utils.logger as logger
log = logger.setup_applevel_logger(is_debug = False)

# Check for missing packages
missing_package = None
try:
    __import__("hdf5view")
except ImportError:
    missing_package = True

# Notify user of missing packages
if missing_package:
    log.warning("The following required packages is missing:")
    log.warning(f" - (\"hdf5view\") \"hdf5view\"")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "hdf5view"])

log.info("All required packages are installed.")

def show_help(ctx, param, value):
    if value and not ctx.resilient_parsing:
        # Display the help information for the command
        click.secho(ctx.get_help(), color=ctx.color)
        # Display examples of script execution
        click.secho("\n-> Script execution example:")
        # Example: Display the contents of an HDF5 file
        click.secho("   python stdatalog_hdf5_viewer.py path\\to\\your\\hdf5_file.h5", fg='cyan')
        ctx.exit()

@click.command()
@click.argument('hdf5_file_path', type=click.Path(exists=True))
@click.option("-h"," --help", is_flag=True, is_eager=True, expose_value=False, callback=show_help, help="Show this message and exit.",)

# Define the main function that will be executed when the script is run
def show_hdf5(hdf5_file_path):
    """
    This function is used to display the contents of an HDF5 file using the HDF5 Viewer.
    
    Parameters:
    hdf5_file_path (str): The path to the HDF5 file to be displayed.
    """
    # Display the contents of the HDF5 file
    subprocess.run(['hdf5view', '-f', hdf5_file_path])

if __name__ == '__main__':
    # Execute the main function
    show_hdf5()