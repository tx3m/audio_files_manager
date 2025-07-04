"""
Manages the metadata for the audio files.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MetadataManager:
    """Handles loading, saving, and querying audio file metadata."""

    def __init__(self, metadata_file: Path):
        """
        Initialize the MetadataManager.

        Args:
            metadata_file: Path to the metadata JSON file.
        """
        self.metadata_file = metadata_file
        self.metadata: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        """Load metadata from file."""
        if self.metadata_file.exists():
            logger.debug(f"Loading metadata from {self.metadata_file}")
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Could not decode JSON from {self.metadata_file}. Starting with empty metadata.")
                return {}
        return {}

    def save(self):
        """Save the current metadata to the JSON file."""
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_file, 'w') as f:
            logger.debug(f"Saving metadata to {self.metadata_file}")
            json.dump(self.metadata, f, indent=4)

    def get(self, button_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the metadata for a specific recording.

        Args:
            button_id: The ID of the button associated with the recording.

        Returns:
            A dictionary containing the recording's metadata, or None if not found.
        """
        return self.metadata.get(button_id)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all recording metadata.

        Returns:
            A dictionary containing metadata for all recordings.
        """
        return self.metadata

    def update_recording(self, button_id: str, data: Dict[str, Any]):
        """
        Update or add a recording's metadata.

        Args:
            button_id: The ID of the button associated with the recording.
            data: A dictionary containing the metadata to save.
        """
        self.metadata[button_id] = data
        self.save()

    def set_read_only(self, button_id: str, read_only: bool):
        """
        Set the read-only status for a recording.

        Args:
            button_id: The ID of the button associated with the recording.
            read_only: True to make the recording read-only, False otherwise.
        """
        if button_id in self.metadata:
            self.metadata[button_id]['read_only'] = read_only
            self.save()

    def get_occupied_sets(self) -> Tuple[Set[str], Set[str]]:
        """
        Get occupied message IDs from metadata for legacy compatibility.

        Returns:
            A tuple containing two sets: (occupied_away_messages, occupied_custom_messages)
        """
        occupied_away = set()
        occupied_custom = set()
        for button_id, meta in self.metadata.items():
            message_type = meta.get('message_type', '')
            if message_type == 'away_message':
                occupied_away.add(button_id)
            elif message_type == 'custom_message':
                occupied_custom.add(button_id)
        return occupied_away, occupied_custom

    def get_messages_by_type(self, message_type: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all messages of a specific type.

        Args:
            message_type: The type of message (e.g., "away_message", "custom_message").

        Returns:
            A dictionary of messages filtered by type.
        """
        return {
            button_id: meta for button_id, meta in self.metadata.items()
            if meta.get('message_type') == message_type
        }

    def get_newest_message_of_type(self, message_type: str) -> Optional[Dict[str, Any]]:
        """
        Find the newest message of a given type based on timestamp.

        Args:
            message_type: The type of message (e.g., "away_message", "custom_message").

        Returns:
            The metadata of the newest message, or None if no messages of that type exist.
        """
        newest_message = None
        latest_time = 0

        for button_id, meta in self.metadata.items():
            if meta.get('message_type') == message_type:
                try:
                    timestamp_str = meta.get("timestamp")
                    if timestamp_str:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        epoch_time = (timestamp - datetime(1970, 1, 1)).total_seconds()

                        if epoch_time > latest_time:
                            latest_time = epoch_time
                            newest_message = meta
                except Exception as e:
                    logger.warning(f"Error processing timestamp for button {button_id}: {e}")
        return newest_message

    def get_message_path(self, audio_file_id: str, message_type: str) -> Optional[str]:
        """
        Get the file path for a specific message.

        Args:
            audio_file_id: The ID of the message.
            message_type: The type of message (e.g., "away_message", "custom_message").

        Returns:
            The file path as a string, or None if not found.
        """
        if audio_file_id:
            message_info = self.get(audio_file_id)
            if message_info and message_info.get('message_type') == message_type:
                return message_info.get('path')
        return None
