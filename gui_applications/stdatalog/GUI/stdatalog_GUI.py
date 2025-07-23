# *****************************************************************************
#  * @file    stdatalog_GUI.py
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

import sys
import os
import argparse

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

# import cProfile
# from pstats import Stats

from PySide6.QtWidgets import QApplication
from PySide6 import QtCore
from PySide6.QtCore import QTimer

from stdatalog_gui.HSD_GUI.HSD_MainWindow import HSD_MainWindow

import stdatalog_core.HSD_utils.logger as logger
log = logger.setup_applevel_logger(is_debug = False)

def load_device_config_after_delay(main_window, config_path):
    """Load device config after a short delay to ensure GUI is fully initialized"""
    def load_config():
        try:
            if main_window.controller and hasattr(main_window.controller, 'load_config'):
                print(f"Auto-loading device configuration from: {config_path}")
                main_window.controller.load_config(config_path)
            else:
                print("Warning: Controller not ready, skipping auto-config load")
        except Exception as e:
            print(f"Error auto-loading device config: {e}")
    
    # Wait 2 seconds after GUI is shown to load config
    QTimer.singleShot(2000, load_config)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='STDatalog GUI Application')
    parser.add_argument('config_file', nargs='?', help='Path to device configuration JSON file')
    args = parser.parse_args()
    
    QApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    
    mainWindow = HSD_MainWindow(app)
    mainWindow.setAppTitle("High Speed Datalog Control SW")
    mainWindow.setAppCredits("High Speed Datalog Control SW")
    mainWindow.setWindowTitle("High Speed Datalog Control SW")
    mainWindow.setAppVersion("v1.0.0")
    mainWindow.setLogMsg("Device is logging --> Board Configuration has been disabled.\nNow you can label your acquisition using the [Tags Information] Component")
    mainWindow.showMaximized()
    
    # Auto-load device config if provided
    if args.config_file:
        if os.path.exists(args.config_file):
            load_device_config_after_delay(mainWindow, args.config_file)
        else:
            print(f"Warning: Device config file not found: {args.config_file}")
    
    app.setAttribute(QtCore.Qt.AA_Use96Dpi)
    app.exec()

if __name__ == "__main__":
    
    # do_profiling = True
    # if do_profiling:
    #     with cProfile.Profile() as pr:
    #         main()

    #     with open('profiling_stats.txt', 'w') as stream:
    #         stats = Stats(pr, stream=stream)
    #         stats.strip_dirs()
    #         stats.sort_stats('time')
    #         stats.dump_stats('.prof_stats')
    #         stats.print_stats()

    main()
