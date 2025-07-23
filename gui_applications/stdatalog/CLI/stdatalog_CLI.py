#!/usr/bin/env python3
# coding: utf-8

import os
import sys
import re
import asyncio
import time
import shutil
import glob
from datetime import datetime

# ROOT:
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# Go up as needed to reach your real project root, e.g.
PROJECT_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, "../../../.."))

# ---- SETTINGS ----
ACQ_TIME = 1    # seconds to log data
DELAY = 14      # seconds to wait
DEVICE_CONFIG_PATH = os.path.join(PROJECT_ROOT, "device_config.json")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "acquisition_data")
SOCKET_PORT = 8888

# Ensure the TUI and SDK are in the path
print("[STARTUP] Adding TUI path to sys.path...")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'TUI')))
print("[STARTUP] Importing stdatalog_TUI...")
from stdatalog_TUI import HSDInfo
print("[STARTUP] Importing HSDLink...")
from stdatalog_core.HSD_link.HSDLink import HSDLink
print("[STARTUP] All imports completed!")

async def async_socket_listener(state):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, state),
        '127.0.0.1', SOCKET_PORT)
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'[IPC] Async IPC server running on {addrs}')
    async with server:
        await server.serve_forever()

async def handle_client(reader, writer, state):
    addr = writer.get_extra_info('peername')
    print(f'[IPC] Connected by {addr}')
    try:
        while True:
            data = await reader.read(32)
            if not data:
                print(f'[IPC] Disconnected by {addr}')
                break
            cmd = data.decode('utf-8').strip().lower()
            if cmd == "start" and not state["running"]:
                state["command"] = "start"
            elif cmd == "stop" and state["running"]:
                state["command"] = "stop"
            elif cmd == "exit":
                state["command"] = "exit"
                break
    except ConnectionResetError:
        print(f"[IPC] Disconnected by {addr}")
    finally:
        writer.close()
        await writer.wait_closed()

def get_next_cut_number(parent_folder):
    """Find the next cut_X number based on existing folders."""
    if not os.path.exists(parent_folder):
        os.makedirs(parent_folder)
        return 1
    cut_nums = []
    for d in os.listdir(parent_folder):
        m = re.match(r'^cut_(\d+)$', d)
        if m:
            cut_nums.append(int(m.group(1)))
    if cut_nums:
        return max(cut_nums) + 1
    return 1

async def cut_logging_task(state):
    # ---- Device/SDK Initialization ----
    print("Initializing STDatalog CLI...")
    tui_flags = HSDInfo.TUIFlags(
        output_folder=OUTPUT_FOLDER,
        sub_datetime_folder=True,
        acq_name="CLI_Log",
        acq_desc="CLI periodic logging",
        file_config=DEVICE_CONFIG_PATH,
        ucf_file="",
        ispu_out_fmt="",
        time_sec=-1,
        interactive_mode=False,
    )
    
    print("Creating HSDInfo instance...")
    try:
        # Run device detection in a thread to avoid blocking the async loop
        def create_hsd_info():
            return HSDInfo(tui_flags)
        
        # Use asyncio to run the blocking call with a timeout
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(create_hsd_info)
            try:
                hsd_info = await asyncio.get_event_loop().run_in_executor(None, lambda: future.result(timeout=30))
                print("HSDInfo created successfully!")
            except concurrent.futures.TimeoutError:
                print("ERROR: Device detection timeout after 30 seconds!")
                print("Please check that your STMicroelectronics device is connected and try again.")
                state["command"] = "exit"
                return
    except Exception as e:
        print(f"ERROR: Failed to initialize device connection: {e}")
        print("Please check that your STMicroelectronics device is connected and try again.")
        state["command"] = "exit"
        return

    if len(hsd_info.device_list) == 0:
        print("No compatible devices connected! Please connect a device and try again.")
        state["command"] = "exit"
        return

    if len(hsd_info.device_list) > 1:
        print(f"Multiple devices found ({len(hsd_info.device_list)}). Using the first one.")

    if hsd_info.selected_device_id is None:
        hsd_info.selected_device_id = 0

    pres_res = HSDLink.get_device_presentation_string(hsd_info.hsd_link, hsd_info.selected_device_id)
    if pres_res is not None:
        board_id = hex(pres_res["board_id"])
        fw_id = hex(pres_res["fw_id"])
        hsd_info.load_device_template(board_id, fw_id)

    hsd_info.update_fw_info()
    hsd_info.update_acq_params()
    hsd_info.upload_device_conf_file()
    hsd_info.update_sensor_list()
    hsd_info.init_sensor_data_counters()
    hsd_info.update_ai_sensor_list()
    hsd_info.update_tag_list()
    hsd_info.init_tag_status_list()
    hsd_info.set_rtc()
    hsd_info.check_output_folder()

    print(f"Connected to device: {hsd_info.selected_fw_info}")
    print(f"Active sensors: {len(hsd_info.sensor_list) if hsd_info.sensor_list else 0}")
    print(f"Output folder: {hsd_info.output_acquisition_path}")
    print(f"Acquisition cycle: {ACQ_TIME}s logging, {DELAY}s pause")
    print(f"Waiting for external commands via IPC socket on port {SOCKET_PORT}...")

    cut_number = get_next_cut_number(OUTPUT_FOLDER)

    while True:
        # Exit condition
        if state["command"] == "exit":
            print("Exiting program. Goodbye.")
            break

        # Start new cut when commanded and not already running
        if state["command"] == "start" and not state["running"]:
            cut_folder = os.path.join(OUTPUT_FOLDER, f"cut_{cut_number}")
            os.makedirs(cut_folder, exist_ok=True)
            
            print(f"Starting acquisition cycle {cut_number}")
            print(f"Cut folder: {cut_folder}")
            
            # Reset output folder to main directory for logging
            hsd_info.tui_flags.output_folder = OUTPUT_FOLDER
            hsd_info.output_acquisition_path = OUTPUT_FOLDER
            hsd_info.update_acq_params()
            hsd_info.check_output_folder()

            print(f"Starting periodic logging: {ACQ_TIME}s log, {DELAY}s pause. Send 'stop' to end safely.")
            state["running"] = True
            state["command"] = None

            while state["running"]:
                # Get list of existing folders before logging
                existing_folders = set()
                if os.path.exists(OUTPUT_FOLDER):
                    existing_folders = {f for f in os.listdir(OUTPUT_FOLDER) 
                                      if os.path.isdir(os.path.join(OUTPUT_FOLDER, f)) 
                                      and not f.startswith('cut_')}
                
                print(f"Starting log cycle...")
                hsd_info.start_log()
                await asyncio.sleep(ACQ_TIME)
                hsd_info.stop_log()
                print("Log cycle complete.")
                
                # Find new folders created during logging
                if os.path.exists(OUTPUT_FOLDER):
                    current_folders = {f for f in os.listdir(OUTPUT_FOLDER) 
                                     if os.path.isdir(os.path.join(OUTPUT_FOLDER, f)) 
                                     and not f.startswith('cut_')}
                    
                    new_folders = current_folders - existing_folders
                    
                    # Move new folders to the cut directory
                    for folder_name in new_folders:
                        src_path = os.path.join(OUTPUT_FOLDER, folder_name)
                        dst_path = os.path.join(cut_folder, folder_name)
                        try:
                            print(f"Moving {folder_name} to {cut_folder}")
                            shutil.move(src_path, dst_path)
                        except Exception as e:
                            print(f"Error moving folder {folder_name}: {e}")
                
                print("Waiting for next cycle...")
                # Wait for DELAY seconds or until a stop command
                for _ in range(DELAY):
                    if state["command"] == "stop":
                        state["running"] = False
                        state["command"] = None
                        break
                    await asyncio.sleep(1)

            print("Stopping acquisition, cleaning up...")
            if hsd_info.is_log_started:
                hsd_info.stop_log()
            print("Done. Waiting for new command, or send 'exit' to quit.")

            cut_number += 1  # increment for next cycle

        await asyncio.sleep(0.1)

async def main():
    state = {"running": False, "command": None, "stop_requested": False}
    await asyncio.gather(
        async_socket_listener(state),
        cut_logging_task(state)
    )

if __name__ == "__main__":
    print("🚀 STDatalog CLI Service Starting...")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path[:3]}...")  # Show first 3 paths
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting by user request.")
