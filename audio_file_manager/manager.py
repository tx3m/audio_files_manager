import logging
import time
import wave
from pathlib import Path
from datetime import datetime
from threading import Event, Thread
from typing import Any, Dict, Optional, Union, Callable, Set

from .backends import get_audio_backend, AudioBackend
from .metadata_manager import MetadataManager
from .file_system_manager import FileSystemManager
from .config import Config

logger = logging.getLogger(__name__)


class AudioFileManager:
    """
    Manages audio recording and playback, coordinating backend, metadata, and file system operations.
    """

    def __init__(self,
                 storage_dir: Optional[Union[str, Path]] = None,
                 metadata_file: Optional[Union[str, Path]] = None,
                 config: Config = Config()):

        # Initialize managers
        self.fs_manager = FileSystemManager(Path(storage_dir) if storage_dir else None)
        
        if metadata_file is None:
            metadata_path = self.fs_manager.get_storage_dir().parent / "metadata.json"
        else:
            metadata_path = Path(metadata_file)
            
        self.metadata_manager = MetadataManager(metadata_path)

        # Audio configuration
        self.config = config
        self.num_buttons = config.num_buttons
        self.message_type = config.message_type

        # Device parameter handling
        input_device = config.input_device
        output_device = config.output_device
        if config.input_device or config.output_device:
            if config.audio_device:
                logger.warning("Both new (input/output_device) and old (audio_device) parameters provided. "
                               "Ignoring audio_device.")
        elif config.audio_device:
            logger.warning("audio_device is deprecated. Use input_device and output_device instead.")
            input_device = config.audio_device
            output_device = config.audio_device

        self.audio_backend: AudioBackend = get_audio_backend(input_device, output_device)

        # Threading and state
        self._recording_thread: Optional[Thread] = None
        self._sound_level_callback: Optional[Callable] = None
        self.current_file: Dict[str, Any] = {}
        self.is_recording = False

        logger.info(
            f"AudioFileManager initialized. Storage: {self.fs_manager.get_storage_dir()}, "
            f"Backend: {type(self.audio_backend).__name__}"
        )

    def set_sound_level_callback(self, callback: Callable[[int], None]):
        """
        Set a callback function to receive sound level updates during recording.

        Args:
            callback: A function that takes an integer (sound level) as an argument.
        """
        self._sound_level_callback = callback

    def get_new_file_id(self, message_type: str) -> Optional[str]:
        """
        Get an available file ID for a given message type.

        Args:
            message_type: The type of message (e.g., "away_message", "custom_message").

        Returns:
            An available file ID as a string, or None if no ID is available.
        """
        occupied_ids = {
            button_id for button_id, meta in self.metadata_manager.get_all().items()
            if meta.get('message_type') == message_type
        }
        
        all_possible_ids = set(str(i) for i in range(1, self.num_buttons + 1))
        available_ids = all_possible_ids - occupied_ids

        if not available_ids:
            logger.warning(f"No available IDs for {message_type}, will overwrite the oldest.")
            # Find the oldest message of this type to overwrite
            oldest_message = None
            oldest_timestamp = float('inf')
            for button_id, meta in self.metadata_manager.get_all().items():
                if meta.get('message_type') == message_type:
                    try:
                        timestamp = datetime.strptime(meta.get("timestamp"), "%Y-%m-%d %H:%M:%S").timestamp()
                        if timestamp < oldest_timestamp:
                            oldest_timestamp = timestamp
                            oldest_message = button_id
                    except (ValueError, TypeError):
                        continue # Skip if timestamp is invalid

            if oldest_message:
                logger.info(f"Overwriting oldest message: {oldest_message}")
                return oldest_message
            else:
                # If no existing messages of this type, just return the first ID
                return "1" # Fallback to 1 if no existing messages to overwrite
        return min(available_ids)

    def record_audio_to_temp(self, button_id: Union[str, int], stop_event: Event,
                             channels: Optional[int] = None, rate: Optional[int] = None) -> Dict[str, Any]:
        """
        Record audio to a temporary file.

        Args:
            button_id: The ID of the button associated with the recording.
            stop_event: An event to signal when to stop recording.
            channels: The number of audio channels.
            rate: The sample rate.

        Returns:
            A dictionary containing information about the recorded file.
        """
        button_id = str(button_id)
        channels = channels or self.config.channels
        rate = rate or self.config.sample_rate

        keyword = self.message_type.lower().replace(" ", "_")
        filename = f"{button_id}_{keyword}_{int(time.time())}.wav"
        temp_path = self.fs_manager.get_temp_dir() / filename
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        pcm_bytes = self.audio_backend.record_audio(
            stop_event=stop_event, channels=channels, rate=rate,
            period_size=self.config.period_size, sound_level_callback=self._sound_level_callback
        )

        duration = len(pcm_bytes) / (rate * channels * 2)  # 2 bytes for S16_LE

        with wave.open(str(temp_path), 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm_bytes)

        return {
            "button_id": button_id, "message_type": self.message_type,
            "duration": round(duration, 2), "temp_path": str(temp_path),
            "timestamp": timestamp, "channels": channels,
            "sample_rate": rate, "audio_format": "wav"
        }

    def start_recording(self, button_id: Union[str, int], stop_callback: Optional[Callable] = None) -> bool:
        """
        Start recording audio in a separate thread.

        Args:
            button_id: The ID of the button associated with the recording.
            stop_callback: A function to call when recording is complete.

        Returns:
            True if recording started successfully, False otherwise.
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return False

        self._stop_event = Event()

        def record_worker():
            self.is_recording = True
            try:
                logger.info(f"Starting recording for button {button_id}, type {self.message_type}")
                self.current_file = self.record_audio_to_temp(button_id, self._stop_event)
                logger.info(f"Recording completed: {self.current_file}")
            except Exception as e:
                logger.error(f"Recording failed: {e}")
                self.current_file = {}
            finally:
                self.is_recording = False
                if stop_callback:
                    stop_callback()

        self._recording_thread = Thread(target=record_worker, daemon=True, name="AudioRecord")
        self._recording_thread.start()
        return True

    def stop_recording(self) -> bool:
        """
        Stop the current recording.

        Returns:
            True if recording was stopped successfully, False otherwise.
        """
        if not self.is_recording:
            logger.warning("No recording in progress to stop")
            return False

        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        if self._recording_thread:
            self._recording_thread.join(timeout=5.0)
            if self._recording_thread.is_alive():
                logger.warning("Recording thread did not stop within timeout")
                return False
        
        logger.info("Recording stopped successfully")
        return True

    def is_recording_active(self) -> bool:
        """
        Check if a recording is currently active.

        Returns:
            True if recording is active, False otherwise.
        """
        return self.is_recording

    def get_current_recording_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the current recording.

        Returns:
            A dictionary containing recording info, or None if not recording.
        """
        return self.current_file if self.is_recording else None

    def play_audio(self, file_path_or_button_id: Union[str, Path, int], blocking: bool = True) -> bool:
        """
        Play an audio file by path or button ID.

        Args:
            file_path_or_button_id: The path to the audio file or the ID of the button.
            blocking: If True, wait for playback to complete.

        Returns:
            True if playback was successful, False otherwise.
        """
        file_path = None
        if isinstance(file_path_or_button_id, (str, int)) and not Path(str(file_path_or_button_id)).exists():
            button_info = self.metadata_manager.get(str(file_path_or_button_id))
            if not button_info or "path" not in button_info:
                logger.error(f"No recording found for button {file_path_or_button_id}")
                return False
            file_path = Path(button_info["path"])
        else:
            file_path = Path(file_path_or_button_id)

        if not file_path.exists():
            logger.error(f"Audio file not found at {file_path}")
            return False

        try:
            self.audio_backend.play_from_file(str(file_path), blocking=blocking)
            return True
        except Exception as e:
            logger.error(f"Failed to play audio file {file_path}: {e}")
            return False

    def finalize_recording(self, temp_path_info: Dict[str, Any]):
        """
        Finalize a recording by moving it to permanent storage and updating metadata.

        Args:
            temp_path_info: A dictionary containing information about the temporary file.
        """
        button_id = str(temp_path_info["button_id"])
        if self.metadata_manager.get(button_id) and self.metadata_manager.get(button_id).get('read_only'):
            logger.warning(f"Finalizing recording blocked: Button {button_id} is read-only.")
            return

        temp_path = Path(temp_path_info["temp_path"])
        final_name = temp_path.name
        final_path = self.fs_manager.get_storage_dir() / final_name

        if self.config.audio_format in ['alaw', 'ulaw']:
            converted_name = temp_path.stem + f"_{self.config.audio_format}.wav"
            converted_path = self.fs_manager.get_storage_dir() / converted_name
            if self.fs_manager.convert_audio_format(temp_path, converted_path, self.config.audio_format,
                                                   temp_path_info["sample_rate"], temp_path_info["channels"]):
                final_path = converted_path
            else:
                logger.error("Audio conversion failed, using original format")
                self.fs_manager.move_to_storage(temp_path, final_name)
        else:
            self.fs_manager.move_to_storage(temp_path, final_name)

        logger.info(f"Finalized recording for button '{button_id}' to {final_path}")

        

        self.metadata_manager.update_recording(button_id, {
            "name": final_path.name, "duration": temp_path_info["duration"],
            "path": str(final_path), "timestamp": temp_path_info["timestamp"],
            "message_type": temp_path_info["message_type"], "audio_format": self.config.audio_format,
            "sample_rate": temp_path_info["sample_rate"], "channels": temp_path_info["channels"],
            "read_only": False, "is_default": False
        })

    def cleanup(self):
        """Clean up resources and stop any running operations."""
        if self._recording_thread and self._recording_thread.is_alive():
            self._stop_event.set()
            self._recording_thread.join(timeout=1.0)
        self.fs_manager.cleanup()

    def discard_recording(self, button_id: Union[str, int]):
        """
        Discard a temporary recording.

        Args:
            button_id: The ID of the button associated with the recording.
        """
        for f in self.fs_manager.get_temp_dir().glob(f"{button_id}_*.wav"):
            f.unlink()

    def set_read_only(self, button_id: Union[str, int], read_only: bool = True):
        """
        Set the read-only status for a recording.

        Args:
            button_id: The ID of the button associated with the recording.
            read_only: True to make the recording read-only, False otherwise.
        """
        self.metadata_manager.set_read_only(str(button_id), read_only)

    def get_recording_info(self, button_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific recording.

        Args:
            button_id: The ID of the button associated with the recording.

        Returns:
            A dictionary containing the recording's metadata, or None if not found.
        """
        return self.metadata_manager.get(str(button_id))

    def list_all_recordings(self) -> Dict[str, Dict[str, Any]]:
        """
        List all recordings.

        Returns:
            A dictionary containing metadata for all recordings.
        """
        return self.metadata_manager.get_all()

    def get_audio_device_info(self) -> Dict[str, Any]:
        """
        Get information about the current audio device.

        Returns:
            A dictionary containing device information.
        """
        return self.audio_backend.get_device_info()

