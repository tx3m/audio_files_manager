"""
Legacy service integration for AudioFileManager.
This module provides compatibility with the legacy MessageRecordService and RecordedMessagesService.
"""

import logging
import os
from pathlib import Path
from datetime import datetime
from threading import Thread
from typing import Optional

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
        self.current_file = {} # This will be populated by audio_manager.current_file

        # Thread handles (kept for compatibility, though direct calls to audio_manager are preferred)
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

    def run(self, message_type):
        """Start recording a message."""
        # Set the message type for this recording
        self.message_type = message_type

        # Get a new ID for recording
        new_id = self.audio_manager.get_new_file_id(self.message_type)
        if new_id is None:
            logger.error(f"Could not get a new file ID for message type: {self.message_type}")
            return

        # Set button ID for UI integration
        if self.nextion_interface:
            if self.message_type == "away_message":
                self._button_id = self.nextion_interface.key_id.AWAY_MESSAGE_CHECKBOX
            elif self.message_type == "custom_message":
                self._button_id = self.nextion_interface.key_id.CUSTOM_MESSAGE_CHECKBOX

        # Start recording using the enhanced manager's encapsulated method
        self.audio_manager.start_recording(
            button_id=new_id,
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
        if self.audio_manager.current_file:
            self.audio_manager.finalize_recording(self.audio_manager.current_file)
        self.is_running = False

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

    #
    # RecordedMessagesService compatibility methods
    #

    def get_message(self, audio_file_type="", audio_file_id="") -> str:
        """Get a message file path."""
        file_to_open = "No file found"

        if audio_file_id:
            # Get specific message by ID
            message_info = self.audio_manager.get_recording_info(audio_file_id)
            if message_info and message_info.get("message_type") == audio_file_type:
                file_to_open = message_info.get("path", "No file found")
        else:
            # Get the newest message of the given type
            newest_message = self.audio_manager.metadata_manager.get_newest_message_of_type(audio_file_type)
            if newest_message:
                file_to_open = newest_message.get("path", "No file found")

        if file_to_open != "No file found":
            logger.info(f"File to be played: {file_to_open}")
        else:
            logger.error(f"Couldn't find requested file of type: {audio_file_type} with ID: {audio_file_id}")

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
            finally:
                self.is_running = False
        else:
            logger.error(f"Couldn't load the requested file of type: {audio_file_type}")
            self._exit_flag = True # This flag seems to be used inconsistently, consider removing if not truly needed

    def get_empty_custom_messages(self):
        """Get a bitmask of missing custom message files."""
        all_custom_messages = self.audio_manager.metadata_manager.get_messages_by_type("custom_message")
        expected_ids = {str(i) for i in range(1, self.audio_manager.num_buttons + 1)} # Use num_buttons from config
        
        found_ids = set(all_custom_messages.keys())
        missing_ids = expected_ids - found_ids
        
        bitmask = 0
        for id_str in missing_ids:
            try:
                bit = int(id_str) - 1
                bitmask |= (1 << bit)
            except ValueError:
                logger.warning(f"Invalid button ID found in metadata: {id_str}")

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

