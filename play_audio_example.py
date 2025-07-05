#!/usr/bin/env python3
"""
Example demonstrating the enhanced play_audio functionality that supports both button IDs and file paths.
"""

import os
import time
from threading import Event
from pathlib import Path
from audio_file_manager import AudioFileManager

def main():
    # Create a temporary directory for this example
    storage_dir = Path(os.path.expanduser("~/.audio_files_example"))
    storage_dir.mkdir(exist_ok=True, parents=True)
    
    print("Initializing AudioFileManager...")
    manager = AudioFileManager(storage_dir=storage_dir)
    
    # Record a sample audio for button1
    button_id = "button1"
    message_type = "greeting"
    
    print(f"Recording audio for button {button_id}...")
    print("Speak for 3 seconds...")
    
    # Record for 3 seconds
    stop_event = Event()
    recording_thread = manager.start_recording(button_id, message_type)
    time.sleep(3)
    manager.stop_recording()
    
    # Finalize the recording
    recording_info = manager.get_current_recording_info()
    if recording_info:
        print(f"Recording completed: {recording_info['duration']:.1f} seconds")
        manager.finalize_recording(recording_info)
        print(f"Recording saved for button {button_id}")
    else:
        print("Recording failed or was empty")
        return
    
    # Play the recording using button ID
    print("\nPlaying audio using button ID...")
    manager.play_audio(button_id)
    
    # Get recording info and play using file path (legacy approach)
    info = manager.get_recording_info(button_id)
    if info:
        print("\nPlaying audio using file path (legacy approach)...")
        manager.play_audio(info["path"])
    
    # Try playing a non-existent button
    print("\nTrying to play non-existent button...")
    result = manager.play_audio("nonexistent_button")
    print(f"Play result: {'Success' if result else 'Failed'}")
    
    # Clean up
    print("\nCleaning up...")
    manager.cleanup()
    print("Done!")

if __name__ == "__main__":
    main()