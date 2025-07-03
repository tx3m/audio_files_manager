#!/usr/bin/env python3
"""
Enhanced Interactive Audio Tester for the AudioFileManager.

This script demonstrates all the features of the enhanced AudioFileManager including:
- Cross-platform audio recording and playback
- Multiple audio formats (PCM, A-law, u-law)
- Sound level monitoring
- Message type management
- Read-only protection
- Default file management
- Legacy service compatibility
"""

import logging
import threading
import time
from typing import Any, Dict, Optional
from pathlib import Path
from audio_file_manager import AudioFileManager, LegacyServiceAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class EnhancedInteractiveAudioTester:
    """
    Enhanced interactive command-line script to test the AudioFileManager.
    Demonstrates all features including legacy compatibility.
    """
    
    def __init__(self):
        self.log = logging.getLogger("EnhancedRecordExample")
        
        # Initialize with enhanced features and separate audio devices
        self.manager = AudioFileManager(
            # Specify separate input and output devices
            input_device="default",   # Device used for recording
            output_device="default",  # Device used for playback
            num_buttons=10,
            audio_format="pcm",  # Can be changed to "alaw" or "ulaw"
            sample_rate=44100,   # Can be changed to 8000 for legacy compatibility
            channels=1
        )
        
        # Set up sound level monitoring
        self.sound_levels = []
        self.manager.set_sound_level_callback(self._sound_level_callback)
        
        # Initialize legacy adapter for demonstration
        self.legacy_adapter = LegacyServiceAdapter(
            audio_manager=self.manager,
            message_path=str(self.manager.storage_dir)
        )
        
        # --- State Variables ---
        self.recording_thread: Optional[threading.Thread] = None
        self.stop_event: Optional[threading.Event] = None
        self.temp_info: Optional[Dict[str, Any]] = None
        self.current_button = "test_button"
        self.current_message_type = "interactive_test"
        
        # Enhanced command set
        self.commands = {
            # Basic recording commands
            "start": self._handle_start,
            "stop": self._handle_stop,
            "cancel": self._handle_cancel,
            "play": self._handle_play,
            "ok": self._handle_ok,
            
            # Enhanced features
            "list": self._handle_list,
            "info": self._handle_info,
            "delete": self._handle_delete,
            "readonly": self._handle_readonly,
            "default": self._handle_default,
            "restore": self._handle_restore,
            
            # Configuration
            "button": self._handle_button,
            "type": self._handle_type,
            "format": self._handle_format,
            "rate": self._handle_rate,
            "status": self._handle_status,
            
            # Legacy compatibility
            "legacy": self._handle_legacy,
            "legacy-play": self._handle_legacy_play,
            
            # Utility
            "help": self._handle_help,
            "exit": self._handle_exit,
        }
    
    def _sound_level_callback(self, level):
        """Callback for sound level monitoring."""
        self.sound_levels.append(level)
        # Show a simple VU meter
        bars = min(40, int(level / 500))
        print(f"\rRecording: [{'#' * bars}{' ' * (40 - bars)}] {level:5d}", end="", flush=True)
    
    def _print_instructions(self):
        """Print comprehensive instructions."""
        print("\n" + "="*60)
        print("   Enhanced Audio File Manager Interactive Test")
        print("="*60)
        print("\nBASIC RECORDING:")
        print("  start    - Begin recording audio")
        print("  stop     - Stop recording and create temporary file")
        print("  cancel   - Stop recording and discard it")
        print("  play     - Play the last recorded temporary file")
        print("  ok       - Confirm and save the recording permanently")
        
        print("\nFILE MANAGEMENT:")
        print("  list     - List all recordings")
        print("  info     - Show info for current button")
        print("  delete   - Delete recording for current button")
        print("  readonly - Toggle read-only protection")
        print("  default  - Set a default recording")
        print("  restore  - Restore default recording")
        
        print("\nCONFIGURATION:")
        print("  button   - Set current button ID")
        print("  type     - Set message type")
        print("  format   - Set audio format (pcm/alaw/ulaw)")
        print("  rate     - Set sample rate")
        print("  status   - Show current configuration")
        
        print("\nLEGACY COMPATIBILITY:")
        print("  legacy   - Record using legacy interface")
        print("  legacy-play - Play using legacy interface")
        
        print("\nUTILITY:")
        print("  help     - Show this help")
        print("  exit     - Quit and cleanup")
        print("="*60)
        
        self._show_current_config()
    
    def _show_current_config(self):
        """Show current configuration."""
        backend_name = type(self.manager.audio_backend).__name__
        device_info = self.manager.get_audio_device_info()
        
        print(f"\nCurrent Configuration:")
        print(f"  Button ID: {self.current_button}")
        print(f"  Message Type: {self.current_message_type}")
        print(f"  Audio Format: {self.manager.audio_format}")
        print(f"  Sample Rate: {self.manager.sample_rate} Hz")
        print(f"  Channels: {self.manager.channels}")
        print(f"  Audio Backend: {backend_name}")
        print(f"  Storage: {self.manager.storage_dir}")
        print(f"  Device Info: {device_info.get('device', 'N/A')}")
    
    def _recording_completed_callback(self):
        """Callback when recording is completed."""
        print("\n")  # Clear VU meter line
        
        if self.manager.current_file:
            self.temp_info = self.manager.current_file.copy()
            self.log.info(f"Recording completed: {self.temp_info.get('duration', 0):.2f} seconds")
        else:
            self.log.error("Recording failed or no audio captured")
            self.temp_info = None
    
    # Basic recording commands
    def _handle_start(self):
        """Start recording."""
        if self.manager.is_recording_active():
            self.log.warning("A recording is already in progress.")
            return
        
        self.sound_levels.clear()
        self.temp_info = None
        
        # Start recording using the encapsulated method
        success = self.manager.start_recording(
            button_id=self.current_button,
            message_type=self.current_message_type,
            stop_callback=self._recording_completed_callback
        )
        
        if success:
            self.log.info(f"Recording started for button {self.current_button}")
            print("\n")  # New line for VU meter
        else:
            self.log.error("Failed to start recording")
    
    def _handle_stop(self):
        """Stop recording."""
        if not self.manager.is_recording_active():
            self.log.warning("No recording is currently active.")
            return
        
        self.log.info("Stopping recording...")
        success = self.manager.stop_recording()
        
        if success:
            self.log.info("Recording stopped successfully")
            # Sound level statistics will be shown in the callback
            if self.sound_levels:
                avg_level = sum(self.sound_levels) / len(self.sound_levels)
                max_level = max(self.sound_levels)
                self.log.info(f"Sound levels - Average: {avg_level:.0f}, Peak: {max_level}")
        else:
            self.log.error("Failed to stop recording properly")
    
    def _handle_cancel(self):
        """Cancel recording."""
        if not self.manager.is_recording_active():
            self.log.warning("No recording is currently active.")
            return
        
        self.log.info("Canceling recording...")
        success = self.manager.stop_recording()
        
        if success:
            self.log.info("Recording canceled and discarded.")
            self.temp_info = None
        else:
            self.log.error("Failed to cancel recording properly")
    
    def _handle_play(self):
        """Play temporary recording."""
        if not self.temp_info:
            self.log.warning("No temporary recording to play. Record something first.")
            return
        
        path_to_play = self.temp_info.get('temp_path')
        if not path_to_play:
            self.log.error("Temporary recording path is missing.")
            return
        
        try:
            self.log.info("Playing the last recording...")
            self.manager.play_audio(path_to_play)
            self.log.info("Playback completed.")
        except Exception as e:
            self.log.error(f"Playback failed: {e}")
    
    def _handle_ok(self):
        """Confirm and save recording."""
        if not self.temp_info:
            self.log.warning("No temporary recording to confirm. Record something first.")
            return
        
        button_id = self.temp_info.get('button_id', 'N/A')
        self.log.info(f"Saving recording for button '{button_id}'...")
        
        try:
            self.manager.finalize_recording(self.temp_info)
            self.log.info("Recording saved permanently.")
            self.temp_info = None
        except Exception as e:
            self.log.error(f"Failed to save recording: {e}")
    
    # Enhanced file management commands
    def _handle_list(self):
        """List all recordings."""
        recordings = self.manager.list_all_recordings()
        if not recordings:
            print("No recordings found.")
            return
        
        print("\nRecordings:")
        print("-" * 80)
        print(f"{'Button':<10} {'Type':<15} {'Duration':<10} {'Read-Only':<10} {'Format':<8} {'File'}")
        print("-" * 80)
        
        for button_id, info in recordings.items():
            duration = info.get('duration', 'N/A')
            if isinstance(duration, (int, float)):
                duration = f"{duration:.2f}s"
            
            print(f"{button_id:<10} {info.get('message_type', 'N/A'):<15} "
                  f"{duration:<10} {str(info.get('read_only', False)):<10} "
                  f"{info.get('audio_format', 'N/A'):<8} {Path(info.get('path', '')).name}")
    
    def _handle_info(self):
        """Show info for current button."""
        info = self.manager.get_recording_info(self.current_button)
        if not info:
            print(f"No recording found for button '{self.current_button}'")
            return
        
        print(f"\nRecording info for button '{self.current_button}':")
        for key, value in info.items():
            print(f"  {key}: {value}")
    
    def _handle_delete(self):
        """Delete recording for current button."""
        info = self.manager.get_recording_info(self.current_button)
        if not info:
            print(f"No recording found for button '{self.current_button}'")
            return
        
        if info.get('read_only'):
            print(f"Cannot delete: button '{self.current_button}' is read-only")
            return
        
        confirm = input(f"Delete recording for button '{self.current_button}'? (y/N): ")
        if confirm.lower() == 'y':
            try:
                Path(info['path']).unlink()
                del self.manager.metadata[self.current_button]
                self.manager._save_metadata()
                print(f"Recording for button '{self.current_button}' deleted.")
            except Exception as e:
                self.log.error(f"Failed to delete recording: {e}")
    
    def _handle_readonly(self):
        """Toggle read-only protection."""
        info = self.manager.get_recording_info(self.current_button)
        if not info:
            print(f"No recording found for button '{self.current_button}'")
            return
        
        current_readonly = info.get('read_only', False)
        new_readonly = not current_readonly
        self.manager.set_read_only(self.current_button, new_readonly)
        print(f"Button '{self.current_button}' read-only: {new_readonly}")
    
    def _handle_default(self):
        """Set a default recording."""
        file_path = input("Enter path to default audio file: ").strip()
        if not file_path:
            return
        
        try:
            self.manager.assign_default(self.current_button, file_path)
            print(f"Default recording set for button '{self.current_button}'")
        except Exception as e:
            self.log.error(f"Failed to set default: {e}")
    
    def _handle_restore(self):
        """Restore default recording."""
        try:
            self.manager.restore_default(self.current_button)
            print(f"Default recording restored for button '{self.current_button}'")
        except Exception as e:
            self.log.error(f"Failed to restore default: {e}")
    
    # Configuration commands
    def _handle_button(self):
        """Set current button ID."""
        button_id = input("Enter button ID: ").strip()
        if button_id:
            self.current_button = button_id
            print(f"Current button set to: {self.current_button}")
    
    def _handle_type(self):
        """Set message type."""
        message_type = input("Enter message type: ").strip()
        if message_type:
            self.current_message_type = message_type
            print(f"Message type set to: {self.current_message_type}")
    
    def _handle_format(self):
        """Set audio format."""
        print("Available formats: pcm, alaw, ulaw")
        audio_format = input("Enter audio format: ").strip().lower()
        if audio_format in ["pcm", "alaw", "ulaw"]:
            self.manager.audio_format = audio_format
            print(f"Audio format set to: {audio_format}")
        else:
            print("Invalid format. Use: pcm, alaw, or ulaw")
    
    def _handle_rate(self):
        """Set sample rate."""
        try:
            rate = int(input("Enter sample rate (e.g., 8000, 44100): ").strip())
            self.manager.sample_rate = rate
            print(f"Sample rate set to: {rate} Hz")
        except ValueError:
            print("Invalid sample rate. Enter a number.")
    
    def _handle_status(self):
        """Show current status."""
        self._show_current_config()
        
        # Show backend info
        device_info = self.manager.get_audio_device_info()
        print(f"\nBackend Details:")
        for key, value in device_info.items():
            print(f"  {key}: {value}")
    
    # Legacy compatibility commands
    def _handle_legacy(self):
        """Record using legacy interface."""
        print(f"Starting legacy recording for {self.current_message_type}...")
        print("Recording will run for 5 seconds...")
        
        try:
            self.legacy_adapter.run(self.current_message_type)
            time.sleep(5)  # Record for 5 seconds
            self.legacy_adapter.exit()
            print("Legacy recording completed.")
        except Exception as e:
            self.log.error(f"Legacy recording failed: {e}")
    
    def _handle_legacy_play(self):
        """Play using legacy interface."""
        try:
            file_path = self.legacy_adapter.get_message(self.current_message_type)
            if file_path != "No file found":
                print(f"Playing legacy recording: {file_path}")
                self.legacy_adapter.play_locally(self.current_message_type)
            else:
                print(f"No legacy recording found for {self.current_message_type}")
        except Exception as e:
            self.log.error(f"Legacy playback failed: {e}")
    
    def _handle_help(self):
        """Show help."""
        self._print_instructions()
    
    def _handle_exit(self):
        """Exit the application."""
        if self.manager.is_recording_active():
            self.log.info("Stopping active recording before exit...")
            self.manager.stop_recording()
        
        # Clean up any resources
        self.manager.cleanup()
        
        return True  # Signal to exit
    
    def run(self):
        """Run the interactive tester."""
        self._print_instructions()
        
        try:
            while True:
                try:
                    command_str = input(f"\n[{self.current_button}]> ").strip().lower()
                    
                    if not command_str:
                        continue
                    
                    handler = self.commands.get(command_str)
                    if handler:
                        if handler():  # Exit command returns True
                            break
                    else:
                        print(f"Unknown command: '{command_str}'. Type 'help' for commands.")
                        
                except KeyboardInterrupt:
                    print("\nInterrupted. Type 'exit' to quit properly.")
                except EOFError:
                    print("\nEOF received. Exiting...")
                    break
                    
        finally:
            self.log.info("Cleaning up...")
            self.manager.cleanup()
            print("Cleanup complete. Goodbye!")


if __name__ == "__main__":
    tester = EnhancedInteractiveAudioTester()
    tester.run()