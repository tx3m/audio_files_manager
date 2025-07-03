#!/usr/bin/env python3
"""
Example script demonstrating the enhanced AudioFileManager with OS abstraction.
This script provides a simple command-line interface for recording, playing, and managing audio files.
"""

import os
import time
import logging
import argparse
from threading import Event
from pathlib import Path
from audio_file_manager import AudioFileManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioManagerDemo:
    """Demo application for the AudioFileManager."""
    
    def __init__(self):
        """Initialize the demo application."""
        # Create a directory in the user's home directory
        home_dir = Path.home()
        self.base_dir = home_dir / ".audio_manager_demo"
        self.storage_dir = self.base_dir / "recordings"
        self.metadata_file = self.base_dir / "metadata.json"
        
        # Ensure directories exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize the manager with separate input/output devices and different audio formats based on OS
        self.manager = AudioFileManager(
            # Specify separate devices for recording and playback
            input_device="default",   # Device used for recording
            output_device="default",  # Device used for playback
            storage_dir=self.storage_dir,
            metadata_file=self.metadata_file,
            num_buttons=10,
            audio_format="pcm"  # Can be "pcm", "alaw", or "ulaw"
        )
        
        # Set up sound level monitoring
        self.last_level = 0
        self.manager.set_sound_level_callback(self._sound_level_callback)
        
        logger.info(f"AudioManagerDemo initialized with backend: {type(self.manager.audio_backend).__name__}")
        logger.info(f"Storage directory: {self.storage_dir}")
        
    def _sound_level_callback(self, level):
        """Callback for sound level updates during recording."""
        self.last_level = level
        # Print a simple VU meter
        bars = min(40, int(level / 500))
        print(f"\rRecording: [{'#' * bars}{' ' * (40 - bars)}] {level}", end="")
    
    def record(self, button_id, message_type="custom", duration=None):
        """Record audio for the specified button."""
        logger.info(f"Recording for button {button_id} ({message_type})...")
        
        stop_event = Event()
        
        # Start recording in a separate thread
        self.manager.record_audio_threaded(button_id, message_type)
        
        try:
            # Record for specified duration or until user interrupts
            if duration:
                print(f"Recording for {duration} seconds...")
                time.sleep(duration)
            else:
                print("Recording... Press Ctrl+C to stop.")
                while True:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nRecording stopped by user.")
        finally:
            # Stop recording
            self.manager.stop_recording()
            print("\nProcessing recording...")
            
            # Wait for recording thread to finish
            time.sleep(1)
            
            # Finalize the recording
            if hasattr(self.manager, 'current_file') and self.manager.current_file:
                self.manager.finalize_recording(self.manager.current_file)
                logger.info(f"Recording finalized: {self.manager.current_file}")
                print(f"Recording saved for button {button_id}")
            else:
                logger.warning("No recording to finalize")
                print("No recording was captured.")
    
    def play(self, button_id):
        """Play the audio for the specified button."""
        info = self.manager.get_recording_info(button_id)
        if not info:
            print(f"No recording found for button {button_id}")
            return
        
        print(f"Playing audio for button {button_id} ({info['message_type']})...")
        self.manager.play_audio(info['path'])
        print("Playback complete.")
    
    def list_recordings(self):
        """List all recordings."""
        recordings = self.manager.list_all_recordings()
        if not recordings:
            print("No recordings found.")
            return
        
        print("\nAvailable Recordings:")
        print("-" * 80)
        print(f"{'Button ID':<10} {'Type':<15} {'Duration':<10} {'Read-Only':<10} {'Path':<30}")
        print("-" * 80)
        
        for button_id, info in recordings.items():
            print(f"{button_id:<10} {info['message_type']:<15} {info.get('duration', 'N/A'):<10} "
                  f"{str(info.get('read_only', False)):<10} {Path(info['path']).name:<30}")
    
    def set_default(self, button_id, file_path):
        """Set a default recording for a button."""
        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {file_path}")
            return
        
        self.manager.assign_default(button_id, path)
        print(f"Default recording set for button {button_id}")
    
    def restore_default(self, button_id):
        """Restore the default recording for a button."""
        self.manager.restore_default(button_id)
        info = self.manager.get_recording_info(button_id)
        if info and 'restored' in info.get('message_type', ''):
            print(f"Default recording restored for button {button_id}")
        else:
            print(f"Could not restore default for button {button_id}")
    
    def set_read_only(self, button_id, read_only=True):
        """Set a recording as read-only."""
        self.manager.set_read_only(button_id, read_only)
        print(f"Button {button_id} set to read-only: {read_only}")
    
    def cleanup(self):
        """Clean up resources."""
        self.manager.cleanup()
        logger.info("AudioManagerDemo cleaned up")


def main():
    """Main entry point for the demo application."""
    parser = argparse.ArgumentParser(description="Audio Manager Demo")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Record command
    record_parser = subparsers.add_parser("record", help="Record audio")
    record_parser.add_argument("button_id", help="Button ID to record for")
    record_parser.add_argument("--type", default="custom", help="Message type (default: custom)")
    record_parser.add_argument("--duration", type=int, help="Recording duration in seconds")
    
    # Play command
    play_parser = subparsers.add_parser("play", help="Play audio")
    play_parser.add_argument("button_id", help="Button ID to play")
    
    # List command
    subparsers.add_parser("list", help="List all recordings")
    
    # Set default command
    default_parser = subparsers.add_parser("set-default", help="Set default recording")
    default_parser.add_argument("button_id", help="Button ID")
    default_parser.add_argument("file_path", help="Path to audio file")
    
    # Restore default command
    restore_parser = subparsers.add_parser("restore-default", help="Restore default recording")
    restore_parser.add_argument("button_id", help="Button ID")
    
    # Set read-only command
    readonly_parser = subparsers.add_parser("set-readonly", help="Set recording as read-only")
    readonly_parser.add_argument("button_id", help="Button ID")
    readonly_parser.add_argument("--value", type=bool, default=True, help="Read-only value (default: True)")
    
    args = parser.parse_args()
    
    demo = AudioManagerDemo()

    try:
        if args.command == "record":
            demo.record(args.button_id, args.type, args.duration)
        elif args.command == "play":
            demo.play(args.button_id)
        elif args.command == "list":
            demo.list_recordings()
        elif args.command == "set-default":
            demo.set_default(args.button_id, args.file_path)
        elif args.command == "restore-default":
            demo.restore_default(args.button_id)
        elif args.command == "set-readonly":
            demo.set_read_only(args.button_id, args.value)
        else:
            parser.print_help()
    finally:
        demo.cleanup()


if __name__ == "__main__":
    main()
