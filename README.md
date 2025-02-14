# stdatalog_examples

![latest tag](https://img.shields.io/github/v/tag/STMicroelectronics/stdatalog_examples.svg?color=brightgreen)

This folder contains a set of examples and tutorials to help you get started with the **[STDATALOG-PYSDK](https://github.com/STMicroelectronics/stdatalog-pysdk)**. Examples are organized in subfolders for different use cases and features:
- **function_tests:** Contains two test scripts that demonstrate the functionalities of the **[stdatalog_core](https://github.com/STMicroelectronics/stdatalog_core)** package. These scripts are intended to be used as a reference for developers who want to use the HSDatalog and HSDLink classes in their projects.
    - **stdatalog_API_examples_HSDatalog.py:** Example to manage and manipulate existing acquisitions and datasets.
    - **stdatalog_API_examples_HSDLink.py:** Example of how to connect to a USB device and control the data logging process. (*NOTE: This script needs a compatible device (board flashed with **[FP-SNS-DATALOG2](https://github.com/STMicroelectronics/fp-sns-datalog2)**) connected to the PC*).
- **how-to_notebooks:** Contains a set of Jupyter notebooks that demonstrate how to use the **[stdatalog_core](https://github.com/STMicroelectronics/stdatalog_core)** package. Run them with the `-h` or `--help` option to visualize the manual and the usage examples.
    - **np_stdatalog_core.ipynb:** Demonstrates how to use the **[stdatalog_core](https://github.com/STMicroelectronics/stdatalog_core)** package to manage acquired data folders extracting and visualizing information and data.
    - **np_stdatalog_converters.ipynb:** Demonstrates how to use the **[stdatalog_core](https://github.com/STMicroelectronics/stdatalog_core)** module focusing on data format conversion features.
- **cli_applications:** Contains a set of ready-to-use command-line applications that demonstrate the functionalities of the **[stdatalog_core](https://github.com/STMicroelectronics/stdatalog_core)**
    - **stdatalog_check_dummy_data.py:** Checks the integrity of dummy data files (*For debug*)
    - **stdatalog_dataframes.py:** Converts data files to pandas dataframes.
    - **stdatalog_data_export.py:** Exports data files to different formats (CSV, TSV, TXT, APACHE PARQUET, HDF5).
    - **stdatalog_data_export_by_tags.py:** Exports data files to different formats (CSV, TSV, TXT) grouped by selected specific tags.
    - **stdatalog_to_nanoedge.py:** Converts data files in a format compatible with **[NanoEdgeAIStudio](https://www.st.com/en/development-tools/nanoedgeaistudio.html)**
    - **stdatalog_to_unico.py:** Converts data files in a format compatible with **[ST MEMS Studio](https://www.st.com/en/development-tools/mems-studio.html)**
    - **stdatalog_to_wav.py:** Converts data files in wav format.
    - **stdatalog_plot.py:** Plots data files.
    - **stdatalog_plot_large.py:** Plots large data files ensuring out-of-core plots for large datasets.
    - **stdatalog_hdf5_viewer.py:** Visualizes the content of HDF5 files.
- **gui_applications:** Contains a set of ready-to-use graphical applications that demonstrate the functionalities of the **[STDATALOG-PYSDK](https://github.com/STMicroelectronics/stdatalog-pysdk)** leveraging the **stdatalog_gui** in sinergy with all the other SDK packages.
    - **stdatalog**: Contains a set of applications that realizes a complete data logging and data monitoring system.
        - **GUI**
            - **stdatalog_GUI.py** GUI application to configure a connected device and control the data logging process visualizing and labeling live data streams.
        - **TUI**
            - **stdatalog_TUI.py** TUI (Text-based User Interface) application to configure a connected device and control the data logging process visualizing and labeling live data streams.
    - **stdatalog_mc** Contains a set of applications that extends the functionalities of the **stdatalog_GUI** with motor control features. This applications are designed for and work with **[FP-IND-DATALOGMC](https://www.st.com/en/embedded-software/fp-ind-datalogmc.html)**.
        - **Datalog**
            - **stdatalog_MC_GUI.py** GUI application based on the **stdatalog_GUI.py** that adds the capability to retrieve and display motor control telemetries and to set motor control parameters.
        - **AI**
            - **stdatalog_MC_AI_GUI.py** GUI application based on the **stdatalog_GUI.py** that adds the capability to display AI classification results on different motor fault conditions.
    - **stdatalog_ultrasound_fft:** This example application is designed to work with the **[UltrasoundFFT](https://github.com/STMicroelectronics/fp-sns-datalog2/tree/main/Projects/STM32U585AI-STWIN.box/Applications/UltrasoundFFT)** application FW contained in the **[FP-SNS-DATALOG2](https://github.com/STMicroelectronics/fp-sns-datalog2)** function pack.
        - **ultrasound_fft_app.py:** GUI application to display analog microphone live data and its FFT. These signals are both streamed from the connected device (The FFT is performed directly on the board).
    - **assisted_segmentation.py"":** GUI application to perform assisted segmentation of an existing acquisition.
- **dtk_plugins:** Contains a set of plugins that can be used to create a data processing pipeline, leveraging the **[stdatalog_dtk](https://github.com/STMicroelectronics/stdatalog_dtk)** (**Data Toolkit** framework) to extend **stdatalog_gui** functionalities. Available plugins provides as example are organized as follow in the "tutorial" folder:
    - **simple:**
        - **HelloWorld:**
            - **HelloWorldPlugin.py:** Simple plugin used to describe the basic structure of a plugin and how it works.
        - **ChainedPlugins:** Example to show how to chain multiple plugins together.
            - **FilterPlugin.py:** Filters accelerometer data computing the norm of the three axis.
            - **ProcessPlugin.py:** Detects if the input filtered data is above a certain threshold.
        - **PluginWithGUI:** Example to show how to create a plugin with a GUI.
            - **PluginWithGUI.py:** Displays the same output as the **FilterPlugin.py** in a dedicated graphical widget.
    - **advanced:**
        - **CSVDataSave:**
            - **CSVDataSavePlugin.py:** Saves the received data in a CSV file.
        - **InclinationGame:**
            - **InclinationGamePlugin.py:** Implements a simple game where the user has to keep a ball within a rectangle by tilting the device.

Furthermore, the **acquisition_examples** folder contains data acquisition examples and device configuration files in UCF and JSON format for SensorTile.box PRO, STWIN.box and STWIN.


## Usage
To run the examples, you need to have the STDATALOG-PYSDK installed on your machine. Please refer to the **[STDATALOG-PYSDK]() How to install STDATALOG-PYSDK** section for detailed instructions on how to install the SDK.
Once the is installed, you can run the examples by navigating to the `stdatalog_examples` folder and running the desired script.

## License
This project is licensed under the BSD 3-Clause License - see the LICENSE.md file for details.