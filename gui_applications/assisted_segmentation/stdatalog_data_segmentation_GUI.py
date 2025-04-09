# *****************************************************************************
#  * @file    stdatalog_data_segmentation_GUI.py
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

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
# Add the example directory to the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import subprocess
from PySide6.QtWidgets import QApplication
from PySide6 import QtCore

import stdatalog_core.HSD_utils.logger as logger
log = logger.setup_applevel_logger(is_debug = False)

log.info("Checking additional required packages...")

# Check for missing packages
missing_packages = {}
required_packages = {
    "skopt": "scikit-optimize",
    "mango": "arm-mango",
    "scipy": "scipy",
    "pywt": "PyWavelets"
}
for package, install_name in required_packages.items():
    try:
        __import__(package)
    except ImportError:
        missing_packages[package] = install_name

# Notify user of missing packages
if missing_packages:
    log.warning("The following required packages are missing:")
    for package in missing_packages:
        log.warning(f" - ({package}) {missing_packages[package]}")
    
    user_input = input("Do you want to install the missing packages? (yes/no): ").strip().lower()
    if user_input in ["yes", "y"]:
        for package in missing_packages:
            version = input(f"Enter the version for {missing_packages[package]} (or press Enter to install the latest version): ").strip()
            if version:
                subprocess.check_call([sys.executable, "-m", "pip", "install", f"{missing_packages[package]}=={version}"])
            else:
                subprocess.check_call([sys.executable, "-m", "pip", "install", missing_packages[package]])
        log.info("All required packages are installed.")
    else:
        log.error("Please install the missing packages and try again.")
        sys.exit(1)
else:
    log.info("All required packages are installed.")

from assisted_segmentation.gui.views import AssistedSegmentationWindow

def main():
    QApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    mainWindow = AssistedSegmentationWindow()
    mainWindow.setWindowTitle("Assisted Segmentation GUI")
    mainWindow.showMaximized()
    app.setAttribute(QtCore.Qt.AA_Use96Dpi)
    app.exec()

if __name__ == "__main__":
    main()
