"""
Legacy service integration for AudioFileManager.
This module provides compatibility with the legacy MessageRecordService and RecordedMessagesService.
"""

import logging
import shutil
import json
import os
from pathlib import Path
from datetime import datetime
from threading import Thread

logger = logging.getLogger(__name__)


class LegacyServiceAdapter:
    """
    Adapter class to provide legacy service functionality using the enhanced AudioFileManager.
    This class integrates both MessageRecordService and RecordedMessagesService functionality.
    """

    def __init__(self, audio_manager, message_path=None, sound_level_updater=None, nextion_interface=None):
        """
        Initialize the legacy service adapter.

        Args:
            audio_manager: The enhanced AudioFileManager instance
            message_path: Path to store message files (default: audio_manager's storage_dir)
            sound_level_updater: Optional sound level updater object
            nextion_interface: Optional Nextion interface for UI integration
        """
        self.audio_manager = audio_manager
        self.message_path = message_path or audio_manager.fs_manager.get_storage_dir()
        self.sound_level_updater = sound_level_updater
        self.nextion_interface = nextion_interface

        # Legacy compatibility attributes
        self._paging_server_callback = None
        self._button_id = -1
        self._exit_flag = False
        self.is_running = False
        self._played_once = False

        # Message type tracking
        self.message_type = "default"
        self.current_file = dict.fromkeys(["id", "filename", "sampling_rate", "encoding", "timestamp"])

        # File paths for JSON backups
        self._away_msg_backup_file = os.path.join(self.message_path, "away_messages.json")
        self._custom_msg_backup_file = os.path.join(self.message_path, "custom_messages.json")

        # Load existing message data
        self._away_messages = self._load_json(self._away_msg_backup_file)
        self._custom_messages = self._load_json(self._custom_msg_backup_file)

        # Thread handles
        self._message_record_thread = None
        self._message_play_thread = None
        self._local_playback_process_handle = None

        # Ensure directories exist
        Path(self.message_path).mkdir(parents=True, exist_ok=True)

        # Set sound level callback
        if self.sound_level_updater:
            self.audio_manager.set_sound_level_callback(self._sound_level_callback)

        logger.info("LegacyServiceAdapter initialized")

    def _sound_level_callback(self, level):
        """Callback for sound level updates during recording."""
        if self.sound_level_updater:
            self.sound_level_updater.set_new_sound_level(direction="input", new_value=level)

    def _load_json(self, file_path):
        """Load JSON data from file."""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load JSON from {file_path}: {e}")
        return {}

    def set_paging_server_callback(self, callback):
        """Set callback for paging server integration."""
        self._paging_server_callback = callback

    def get_audio_levels(self) -> dict:
        """Get audio levels for input/output."""
        if self._paging_server_callback:
            self._paging_server_callback(new_active_obj=self, obj_type='input')
        return dict(input_levels={}, output_levels={})

    #
    # MessageRecordService compatibility methods
    #

    def _generate_new_file_name(self) -> None:
        """Generate a new file name for recording."""
        new_id = self._get_new_id()
        if self.message_type == "away_message":
            if self.nextion_interface:
                self._button_id = self.nextion_interface.key_id.AWAY_MESSAGE_CHECKBOX
        elif self.message_type == "custom_message":
            if self.nextion_interface:
                self._button_id = self.nextion_interface.key_id.CUSTOM_MESSAGE_CHECKBOX

        file_name = self.message_type + new_id + ".wav"
        full_path = os.path.join(self.message_path, file_name)
        logger.info(f"Full path for new file: {full_path}")

        # Create empty file
        if os.path.exists(full_path):
            os.remove(full_path)
            logger.info("Overwriting existing file")
        else:
            logger.info("Creating new file...")

        open(full_path, mode="w").close()  # create new file
        self.current_file = {
            "id": new_id,
            "filename": file_name,
            "timestamp": self._create_timestamp(),
            "sampling_rate": self.audio_manager.config.sample_rate,
            "encoding": self.audio_manager.config.audio_format
        }

    def _get_new_id(self) -> str:
        """Get a new ID for recording."""
        return self.audio_manager.get_new_file_id(self.message_type)

    @staticmethod
    def _create_timestamp() -> str:
        """Create a timestamp string."""
        return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def update_json_backup(self, message_type=""):
        """Update JSON backup with current file information."""
        logger.info("Updating json backup file information...")
        if message_type == "away_message":
            try:
                self._away_messages[self.current_file["id"]] = {
                    "filename": self.current_file["filename"],
                    "sampling_rate": self.audio_manager.config.sample_rate,
                    "encoding": self.audio_manager.config.audio_format,
                    "timestamp": self.current_file["timestamp"]
                }
                self.save(self._away_msg_backup_file)
            except Exception as e:
                logger.warning(f"Couldn't write to the backup file: {e}")

        elif message_type == "custom_message":
            try:
                self._custom_messages[self.current_file["id"]] = {
                    "filename": self.current_file["filename"],
                    "sampling_rate": self.audio_manager.config.sample_rate,
                    "encoding": self.audio_manager.config.audio_format,
                    "timestamp": self.current_file["timestamp"]
                }
                self.save(self._custom_msg_backup_file)
            except Exception as e:
                logger.warning(f"Couldn't write to the backup file: {e}")
        else:
            logger.error(f"Unsupported message type: {message_type}")
            raise Exception(f"Message type [{message_type}] not supported!!!")

    def save(self, backup_file):
        """Save message data to backup file."""
        with open(backup_file, "w") as f:
            if self.message_type == "away_message":
                json.dump(self._away_messages, f)
            elif self.message_type == "custom_message":
                json.dump(self._custom_messages, f)
        logger.info(f"Backup information was stored to {backup_file}")

    def run(self, message_type):
        """Start recording a message."""
        # Set the message type for this recording
        self.message_type = message_type

        # Generate a new file name
        self._generate_new_file_name()

        # Start recording using the enhanced manager's encapsulated method
        self.audio_manager.start_recording(
            button_id=self.current_file["id"],
            message_type=message_type,
            stop_callback=self._recording_completed_callback
        )

        self.is_running = True

        # Start sound level updater if available
        if self.sound_level_updater and not hasattr(self.sound_level_updater, '_thread'):
            self.sound_level_updater._thread = Thread(
                target=self.sound_level_updater.run,
                daemon=True,
                name="SoundLvlUpdater"
            )
            self.sound_level_updater._thread.start()

    def _recording_completed_callback(self):
        """Called when recording is completed."""
        # Get the recording info from the manager
        if self.audio_manager.current_file:
            # Update the current file with the recording info
            self.current_file.update({
                "duration": self.audio_manager.current_file.get("duration", 0),
                "temp_path": self.audio_manager.current_file.get("temp_path", ""),
                "timestamp": self.audio_manager.current_file.get("timestamp", self._create_timestamp())
            })

            # Process the recording (convert format if needed and save to final location)
            self._process_recording()

            # Update JSON backup
            self.update_json_backup(self.message_type)

        self.is_running = False

    def _process_recording(self):
        """Process the recording (convert format if needed and save to final location)."""
        if not self.audio_manager.current_file:
            return

        temp_path = self.audio_manager.current_file.get("temp_path")
        if not temp_path or not Path(temp_path).exists():
            logger.warning("No temporary recording file found")
            return

        # Get the final output path
        output_file = os.path.join(self.message_path, self.current_file["filename"])

        # Convert audio format if needed
        if self.audio_manager.config.audio_format in ["alaw", "ulaw"]:
            success = self.audio_manager.fs_manager.convert_audio_format(
                Path(temp_path),
                Path(output_file),
                self.audio_manager.config.audio_format,
                self.audio_manager.config.sample_rate,
                self.audio_manager.config.channels
            )
            if not success:
                # If conversion fails, just copy the file
                shutil.copy(temp_path, output_file)
        else:
            # Just copy the file
            shutil.copy(temp_path, output_file)

    def exit(self):
        """Stop recording and clean up resources."""
        self._exit_flag = True

        # Stop any active recording using the manager's method
        if self.audio_manager.is_recording_active():
            self.audio_manager.stop_recording()
            logger.info("Stopped active recording")

        # Stop sound level updater if running
        if self.sound_level_updater and hasattr(self.sound_level_updater, '_thread'):
            self.sound_level_updater.exit()
            self.sound_level_updater._thread.join()
            self.sound_level_updater._thread = None
            logger.info("Closed Sound level updater thread")

        # Reset UI elements
        self._reset_buttons_default_state()

        # Reset flags
        self._exit_flag = False
        self.is_running = False

    def _reset_buttons_default_state(self):
        """Reset button states to default."""
        if self.nextion_interface and self._button_id != -1:
            self._sync_text_leds(self._button_id, "reset")
            self._button_id = -1

    def _sync_text_leds(self, button, operation):
        """Sync text LEDs with button states."""
        if not self.nextion_interface:
            return

        sync = False
        if operation == "set":
            self.nextion_interface.buttons_state.set_button(button)
            sync = True
        elif operation == "reset":
            self.nextion_interface.buttons_state.reset_button(button)
            sync = True
        elif operation == "flip":
            self.nextion_interface.buttons_state.flip_button(button)
            sync = True

        if sync and self.nextion_interface.nextion_panel_sync_leds_callback_fn:
            self.nextion_interface.nextion_panel_sync_leds_callback_fn()

    # The _record_audio method has been removed and replaced by the encapsulated recording methods
    # in the AudioFileManager. The recording process is now managed by:
    # 1. The start_recording method in AudioFileManager
    # 2. The _recording_completed_callback method in LegacyServiceAdapter
    # 3. The _process_recording method in LegacyServiceAdapter

    #
    # RecordedMessagesService compatibility methods
    #

    def _load_newest_files(self):
        """Load newest message files."""
        from datetime import datetime

        # Process away messages
        if self._away_messages:
            newest_away_id = self._find_newest_message_id(self._away_messages)
            if newest_away_id:
                # Use self.current_file instead of self._current_file
                self.current_file = {
                    "away_message": self._away_messages[newest_away_id]["filename"]
                }

        # Process custom messages
        if self._custom_messages:
            newest_custom_id = self._find_newest_message_id(self._custom_messages)
            if newest_custom_id:
                if not hasattr(self, 'current_file') or not self.current_file:
                    self.current_file = {}
                self.current_file["custom_message"] = self._custom_messages[newest_custom_id]["filename"]

    def _find_newest_message_id(self, messages_dict):
        """Find the newest message ID based on timestamp."""
        newest_id = None
        latest_time = 0

        for msg_id, msg_data in messages_dict.items():
            try:
                timestamp = msg_data["timestamp"]
                utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                epoch_time = (utc_time - datetime(1970, 1, 1)).total_seconds()

                if epoch_time > latest_time:
                    latest_time = epoch_time
                    newest_id = msg_id
            except Exception as e:
                logger.warning(f"Error processing message timestamp: {e}")

        return newest_id

    def _refresh_files_lists(self):
        """Refresh file lists from JSON backups."""
        self._away_messages = self._load_json(self._away_msg_backup_file)
        self._custom_messages = self._load_json(self._custom_msg_backup_file)

    def get_message(self, audio_file_type="", audio_file_id=""):
        """Get a message file path."""
        self._refresh_files_lists()
        self._load_newest_files()

        file_to_open = "No file found"

        if audio_file_type == "away_message" and self._away_messages:
            if audio_file_id == "":  # Load the newest file
                # Use self.current_file instead of self._current_file
                audio_file_name = self.current_file.get("away_message")
            else:  # Load the particular file requested
                audio_file_name = self._away_messages.get(audio_file_id, {}).get("filename")

            if audio_file_name:
                file_to_open = os.path.join(self.message_path, audio_file_name)
                logger.info(f"File to be played: {file_to_open}")

        elif audio_file_type == "custom_message" and self._custom_messages:
            if audio_file_id == "":  # Load the newest file
                # Use self.current_file instead of self._current_file
                audio_file_name = self.current_file.get("custom_message")
            else:
                audio_file_name = self._custom_messages.get(audio_file_id, {}).get("filename")

            if audio_file_name:
                file_to_open = os.path.join(self.message_path, audio_file_name)
                logger.info(f"File to be played: {file_to_open}")

        return file_to_open

    def play_locally(self, audio_file_type="", audio_file_id=""):
        """Play a message file locally."""
        file_to_open = self.get_message(audio_file_type, audio_file_id)

        if file_to_open != "No file found":
            self.is_running = True
            try:
                logger.info(f"Playing locally: {file_to_open}")
                self.audio_manager.play_audio(file_to_open)
                self._played_once = True
            except Exception as e:
                logger.error(f"Error playing file: {e}")
                self.is_running = False
        else:
            logger.error(f"Couldn't load the requested file of type: {audio_file_type}")
            self._exit_flag = True

        self.is_running = False

    def get_empty_custom_messages(self):
        """Get a bitmask of missing custom message files."""
        self._refresh_files_lists()
        expected_ids = {str(i) for i in range(1, 17)}
        bitmask = 0xffff

        if self._custom_messages:
            found_ids = set(self._custom_messages.keys())
            missing_ids = expected_ids - found_ids
            bitmask = 0
            for id in missing_ids:
                bit = int(id) - 1
                bitmask |= (1 << bit)

        empty_bitmask = f"0x{bitmask:04X}"
        return empty_bitmask

    def force_exit(self):
        """Force exit any ongoing operations."""
        self._exit_flag = True
        self.is_running = False

    @property
    def played_once(self):
        """Get played_once flag."""
        return self._played_once

    @played_once.setter
    def played_once(self, new_value: bool):
        """Set played_once flag."""
        if self._played_once != new_value:
            logger.debug(f"Changing self._played_once to {new_value}")
            self._played_once = new_value

    def finished(self):
        """
        Ends the operation after the playback has finished and returns True
        Otherwise immediately returns False

        This method is required for compatibility with the legacy RecordedMessagesService.
        """
        # Since we're using the AudioFileManager's play_audio method which is blocking,
        # we can determine if playback is finished based on is_running flag
        if not self.is_running and self._played_once:
            self._played_once = True
            return True
        return False
