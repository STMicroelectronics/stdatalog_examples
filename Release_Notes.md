---
pagetitle: Release Notes for stdatalog_examples 
lang: en
header-includes: <link rel="icon" type="image/x-icon" href="_htmresc/favicon.png" />
---

::: {.row}
::: {.col-sm-12 .col-lg-4}

<center> 
# Release Notes for <mark>stdatalog_examples</mark> 
Copyright &copy; 2025 STMicroelectronics
    
[![ST logo](_htmresc/st_logo_2020.png)](https://www.st.com){.logo}
</center>


# Purpose

This folder contains a set of examples and tutorials to help you get started with the **[STDATALOG-PYSDK](https://github.com/STMicroelectronics/stdatalog-pysdk)**. Examples are organized in subfolders for different use cases and features:

:::

::: {.col-sm-12 .col-lg-8}
# Update History

::: {.collapse}
<input type="checkbox" id="collapse-section6" checked aria-hidden="true">
<label for="collapse-section6" aria-hidden="true">v1.4.0 / 15-May-26</label>
<div>


## Main Changes

### Maintenance Release

- Refactored and enhance documentation across multiple plugins
  - Removed unnecessary whitespace and added newlines for code consistency in 0_ML_AI_plugin.py.
  - Added pylint skip directive to dToF_PeopleCounting plugins to suppress warnings.
  - Improved docstrings in CSVDataSavePlugin.py for clarity on methods and parameters.
  - Enhanced comments and docstrings in InclinationGamePlugin.py for better understanding of functionality.
  - Updated FilterPlugin.py and ProcessPlugin.py with detailed docstrings and comments for clarity.
  - Added initialization messages and improved logging in HelloWorldPlugin and its status variant.
  - Implemented GUI functionality in FilterPlugin_GUI.py with appropriate docstrings and comments.
- Updated examples and documentation to support unified JSON configuration for MLC and ISPU sensors
- Added JSON configuration examples
- Refactored sensor streaming example
  - Deleted the original stdatalog_sensors_streaming.py file.
  - Introduced stdatalog_sensors_streaming.py for a combined streaming example supporting USB and serial transports.
  - Created stdatalog_sensors_streaming_common.py to encapsulate shared logic for streaming.
  - Added stdatalog_sensors_streaming_serial.py for serial-specific streaming functionality.
  - Introduced stdatalog_sensors_streaming_usb.py for USB/PnPL streaming example.


</div>
:::

::: {.collapse}
<input type="checkbox" id="collapse-section5" aria-hidden="true">
<label for="collapse-section5" aria-hidden="true">v1.3.0 / 14-Nov-25</label>
<div>


## Main Changes

### Maintenance Release and Product Update

- Reshaped GUI examples for FP-IND-DATALOGMC: created dedicated folder and scripts for CubeAI and NanoEdgeAI Studio applications
- Added new example: stdatalog_sensors_streaming.py
- Updated acquisition example folder


</div>
:::

::: {.collapse}
<input type="checkbox" id="collapse-section4" aria-hidden="true">
<label for="collapse-section4" aria-hidden="true">v1.2.1 / 29-Aug-25</label>
<div>


## Main Changes

### Patch Release

- Solved issue #1 - pull request #2: accepted proposal from @YumTaha
- Added stdatalog_API_examples_SerialLink.py example in stdatalog_examples\function_tests


</div>
:::

::: {.collapse}
<input type="checkbox" id="collapse-section3" aria-hidden="true">
<label for="collapse-section3" aria-hidden="true">v1.2.0 / 24-Jul-25</label>
<div>


## Main Changes

### Maintenance Release

- Solved issue #3 Documentation Mismatch in Assisted Segmentation README


</div>
:::

::: {.collapse}
<input type="checkbox" id="collapse-section2" aria-hidden="true">
<label for="collapse-section2" aria-hidden="true">v1.1.0 / 20-Jun-25</label>
<div>


## Main Changes

### Maintenance Release

- Added support to Python 3.13
- Updated SDK examples with plots: use Plotly instead of matplotlib
- Fixed separator char ('\\' to '/')
- Fixed trimming in MC_AI_dataset_creation application


</div>
:::

::: {.collapse}
<input type="checkbox" id="collapse-section1" aria-hidden="true">
<label for="collapse-section1" aria-hidden="true">v1.0.0 / 17-Jan-25</label>
<div>


## Main Changes

### First official release


</div>
:::

:::
:::

<footer class="sticky">
::: {.columns}
::: {.column width="95%"}
For complete documentation,
visit: [www.st.com](https://github.com/STMicroelectronics/stdatalog-pysdk)
:::
::: {.column width="5%"}
<abbr title="Based on template cx566953 version 2.0">Info</abbr>
:::
:::
</footer>
