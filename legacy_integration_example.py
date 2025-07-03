#!/usr/bin/env python3
"""
Example script demonstrating how to use the LegacyServiceAdapter with AudioFileManager.
This shows how to integrate with legacy code that expects MessageRecordService or RecordedMessagesService.
"""

import time
import logging
import argparse
from pathlib import Path
from threading import Event

from audio_file_manager import AudioFileManager, LegacyServiceAdapter

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MockSoundLevelUpdater:
    """Mock sound level updater for demonstration purposes."""
    
    def __init__(self):
        self.current_level = 0
    
    def set_new_sound_level(self, direction, new_value):
        self.current_level = new_value
        print(f"Sound level ({direction}): {new_value}")
    
    def run(self):
        """Run the updater."""
        logger.info("Sound level updater running")
        while not hasattr(self, 'exit_flag') or not self.exit_flag:
            time.sleep(0.1)
    
    def exit(self):
        """Exit the updater."""
        self.exit_flag = True


class MockNextionInterface:
    """Mock Nextion interface for demonstration purposes."""
    
    class KeyID:
        """Mock key IDs."""
        AWAY_MESSAGE_CHECKBOX = 1
        CUSTOM_MESSAGE_CHECKBOX = 2
    
    class ButtonState:
        """Mock button state."""
        def __init__(self):
            self.buttons = {}
        
        def set_button(self, button_id):
            self.buttons[button_id] = True
            print(f"Button {button_id} set")
        
        def reset_button(self, button_id):
            self.buttons[button_id] = False
            print(f"Button {button_id} reset")
        
        def flip_button(self, button_id):
            self.buttons[button_id] = not self.buttons.get(button_id, False)
            print(f"Button {button_id} flipped to {self.buttons[button_id]}")
    
    def __init__(self):
        self.key_id = self.KeyID()
        self.buttons_state = self.ButtonState()
        self.nextion_panel_sync_leds_callback_fn = self.sync_leds
    
    def sync_leds(self):
        """Sync LEDs with button states."""
        print("Syncing LEDs with button states")


def demo_legacy_record():
    """Demonstrate legacy recording functionality."""
    print("\n=== Legacy Recording Demo ===")
    
    # Create temporary directory for testing
    storage_dir = Path.home() / ".audio_manager_demo" / "legacy_demo"
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize the AudioFileManager
    manager = AudioFileManager(
        storage_dir=storage_dir,
        audio_format="alaw",  # Legacy format
        sample_rate=8000,     # Legacy sample rate
        channels=1
    )
    
    # Create mock objects
    sound_level_updater = MockSoundLevelUpdater()
    nextion_interface = MockNextionInterface()
    
    # Create the legacy adapter
    legacy_service = LegacyServiceAdapter(
        audio_manager=manager,
        message_path=str(storage_dir),
        sound_level_updater=sound_level_updater,
        nextion_interface=nextion_interface
    )
    
    try:
        # Record a message using legacy interface
        print("\n1. Recording away message...")
        legacy_service.run("away_message")
        
        # Wait for recording to complete
        print("Recording for 3 seconds...")
        time.sleep(3)
        
        # Stop recording
        legacy_service.exit()
        print("Recording stopped")
        
        # Wait for processing to complete
        time.sleep(1)
        
        # Play the recorded message
        print("\n2. Playing back the recorded message...")
        file_path = legacy_service.get_message("away_message")
        if file_path != "No file found":
            print(f"Playing file: {file_path}")
            legacy_service.play_locally("away_message")
        else:
            print("No message found to play")
        
        # Check empty message slots
        print("\n3. Checking empty message slots...")
        empty_mask = legacy_service.get_empty_custom_messages()
        print(f"Empty custom message slots bitmask: {empty_mask}")
        
        print("\n✅ Legacy integration demo completed successfully!")
        
    finally:
        # Clean up
        legacy_service.exit()
        manager.cleanup()


def demo_direct_integration():
    """Demonstrate direct integration with AudioFileManager."""
    print("\n=== Direct Integration Demo ===")
    
    # Create temporary directory for testing
    storage_dir = Path.home() / ".audio_manager_demo" / "direct_demo"
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize the AudioFileManager
    manager = AudioFileManager(
        storage_dir=storage_dir,
        audio_format="pcm",
        sample_rate=44100,
        channels=1
    )
    
    try:
        # Record audio directly with AudioFileManager
        print("\n1. Recording audio directly...")
        stop_event = Event()
        
        # Start recording in a thread
        def record_and_finalize():
            recording_info = manager.record_audio_to_temp(
                button_id="1",
                message_type="greeting",
                stop_event=stop_event
            )
            manager.finalize_recording(recording_info)
            print(f"Recording finalized: {recording_info}")
        
        import threading
        record_thread = threading.Thread(target=record_and_finalize)
        record_thread.start()
        
        # Record for a few seconds
        print("Recording for 3 seconds...")
        time.sleep(3)
        
        # Stop recording
        stop_event.set()
        record_thread.join()
        print("Recording stopped")
        
        # Play back the recording
        print("\n2. Playing back the recording...")
        info = manager.get_recording_info("1")
        if info:
            print(f"Playing file: {info['path']}")
            manager.play_audio(info['path'])
        else:
            print("No recording found")
        
        print("\n✅ Direct integration demo completed successfully!")
        
    finally:
        # Clean up
        manager.cleanup()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Legacy Integration Demo")
    parser.add_argument("--mode", choices=["legacy", "direct", "both"], default="both",
                      help="Demo mode: legacy, direct, or both")
    
    args = parser.parse_args()
    
    if args.mode in ["legacy", "both"]:
        demo_legacy_record()
    
    if args.mode in ["direct", "both"]:
        demo_direct_integration()


if __name__ == "__main__":
    main()