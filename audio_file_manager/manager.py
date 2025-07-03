import json
import time
import logging
import wave
import shutil
import subprocess
import os
from pathlib import Path
from datetime import datetime
import tempfile
from threading import Event, Thread
from typing import Any, Dict, Optional, Union, Callable, Set
from .backends import get_audio_backend, AudioBackend

logger = logging.getLogger(__name__)


class AudioFileManager:
    """
    Enhanced AudioFileManager with legacy functionality and OS abstraction.
    
    Features:
    - Cross-platform audio recording and playback
    - Message type management (away_message, custom_message, etc.)
    - File ID management with occupied tracking
    - Audio format conversion (PCM, A-law, u-law)
    - Threading support for background operations
    - Sound level monitoring
    - Read-only protection and default file management
    """
    
    MAX_FILES_PER_TYPE = set([str(i) for i in range(1, 5)])  # Legacy compatibility
    
    def __init__(self, 
                 storage_dir: Optional[Union[str, Path]] = None, 
                 metadata_file: Optional[Union[str, Path]] = None, 
                 num_buttons: int = 16,
                 audio_device: Optional[str] = None,
                 sample_rate: int = 44100,
                 channels: int = 1,
                 audio_format: str = "pcm",  # pcm, alaw, ulaw
                 period_size: int = 1024):
        
        # Directory setup
        if storage_dir is None:
            base_dir = Path.home() / ".audio_files_manager"
            storage_dir = base_dir / "storage"
            if metadata_file is None:
                metadata_file = base_dir / "metadata.json"

        self.storage_dir = Path(storage_dir)
        self.metadata_file = Path(metadata_file) if metadata_file else self.storage_dir.parent / "metadata.json"
        self._temp_dir_obj = tempfile.TemporaryDirectory(prefix="audio_staging_")
        self.temp_dir = Path(self._temp_dir_obj.name)
        
        # Audio configuration
        self.num_buttons = num_buttons
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_format = audio_format.lower()
        self.period_size = period_size
        
        # Initialize audio backend
        self.audio_backend: AudioBackend = get_audio_backend(audio_device)
        
        # Legacy compatibility - occupied message tracking
        self.occupied_away_messages: Set[str] = set()
        self.occupied_custom_messages: Set[str] = set()
        
        # Threading support
        self._exit_flag = False
        self._recording_thread: Optional[Thread] = None
        self._sound_level_callback: Optional[Callable] = None
        
        # Current recording state
        self.current_file: Dict[str, Any] = {}
        self.is_recording = False
        
        # Initialize storage
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metadata: Dict[str, Dict[str, Any]] = self._load_metadata()
        self._load_occupied_sets()
        
        logger.info(f"AudioFileManager initialized. Storage: {self.storage_dir}, Backend: {type(self.audio_backend).__name__}")

    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Load metadata from file."""
        if self.metadata_file.exists():
            logger.debug(f"Loading metadata from {self.metadata_file}")
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_metadata(self):
        """Save metadata to file."""
        with open(self.metadata_file, 'w') as f:
            logger.debug(f"Saving metadata to {self.metadata_file}")
            json.dump(self.metadata, f, indent=4)

    def _load_occupied_sets(self):
        """Load occupied message IDs from metadata for legacy compatibility."""
        for button_id, meta in self.metadata.items():
            message_type = meta.get('message_type', '')
            if message_type == 'away_message':
                self.occupied_away_messages.add(button_id)
            elif message_type == 'custom_message':
                self.occupied_custom_messages.add(button_id)

    def set_sound_level_callback(self, callback: Callable[[int], None]):
        """Set callback for sound level monitoring during recording."""
        self._sound_level_callback = callback

    def get_new_file_id(self, message_type: str) -> Optional[str]:
        """
        Get an available file ID for the given message type.
        Legacy compatibility method.
        """
        if message_type == "away_message":
            available_ids = self.MAX_FILES_PER_TYPE - self.occupied_away_messages
        elif message_type == "custom_message":
            available_ids = self.MAX_FILES_PER_TYPE - self.occupied_custom_messages
        else:
            # For other message types, use button IDs
            occupied = set(self.metadata.keys())
            available_ids = set(str(i) for i in range(1, self.num_buttons + 1)) - occupied
        
        if not available_ids:
            logger.warning(f"No available IDs for {message_type}, will overwrite")
            if message_type == "away_message":
                self.occupied_away_messages.clear()
                available_ids = self.MAX_FILES_PER_TYPE
            elif message_type == "custom_message":
                self.occupied_custom_messages.clear()
                available_ids = self.MAX_FILES_PER_TYPE
            else:
                return None
        
        return min(available_ids)

    def record_audio_to_temp(self, button_id: Union[str, int], message_type: str, stop_event: Event, 
                           channels: Optional[int] = None, rate: Optional[int] = None) -> Dict[str, Any]:
        """
        Records audio from the system microphone to a temporary WAV file until the provided stop_event is triggered.
        Enhanced version with sound level monitoring and backend abstraction.
        """
        button_id = str(button_id)
        channels = channels or self.channels
        rate = rate or self.sample_rate
        
        keyword = message_type.lower().replace(" ", "_")
        filename = f"{button_id}_{keyword}_{int(time.time())}.wav"
        temp_path = self.temp_dir / filename
        timestamp = datetime.utcnow().isoformat()
        
        # Record audio using the backend
        pcm_bytes = self.audio_backend.record_audio(
            stop_event=stop_event,
            channels=channels,
            rate=rate,
            period_size=self.period_size,
            sound_level_callback=self._sound_level_callback
        )
        
        # Calculate duration
        sample_width_bytes = 2  # S16_LE format
        duration = len(pcm_bytes) / (rate * channels * sample_width_bytes)
        
        # Write to WAV file
        with wave.open(str(temp_path), 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width_bytes)
            wf.setframerate(rate)
            wf.writeframes(pcm_bytes)

        return {
            "button_id": button_id,
            "message_type": message_type,
            "duration": round(duration, 2),
            "temp_path": str(temp_path),
            "timestamp": timestamp,
            "channels": channels,
            "sample_rate": rate,
            "audio_format": "wav"
        }

    def record_audio_threaded(self, button_id: Union[str, int], message_type: str, 
                            stop_callback: Optional[Callable] = None) -> Thread:
        """
        Start recording in a separate thread. Legacy compatibility method.
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return None
        
        self._exit_flag = False
        stop_event = Event()
        
        def record_worker():
            try:
                self.is_recording = True
                self.current_file = self.record_audio_to_temp(button_id, message_type, stop_event)
                logger.info(f"Recording completed: {self.current_file}")
            except Exception as e:
                logger.error(f"Recording failed: {e}")
            finally:
                self.is_recording = False
                if stop_callback:
                    stop_callback()
        
        self._recording_thread = Thread(target=record_worker, daemon=True, name="AudioRecord")
        self._recording_thread.start()
        
        # Store stop event for external control
        self._stop_event = stop_event
        return self._recording_thread

    def stop_recording(self):
        """Stop the current recording."""
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
        self._exit_flag = True

    def play_audio(self, file_path: Union[str, Path]) -> None:
        """
        Plays the audio from the given WAV file using the audio backend.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Cannot play audio: file not found at {path}")
            return

        try:
            with wave.open(str(path), 'rb') as wf:
                samplerate = wf.getframerate()
                channels = wf.getnchannels()
                n_frames = wf.getnframes()
                audio_bytes = wf.readframes(n_frames)

            logger.info(f"Playing audio from {path}...")
            self.audio_backend.play_audio(audio_bytes, channels, samplerate)
            logger.info("Playback finished.")
        except Exception as e:
            logger.error(f"Failed to play audio file {path}: {e}")

    def finalize_recording(self, temp_path_info: Dict[str, Any]) -> None:
        """
        Finalize a recording by moving it to permanent storage and updating metadata.
        Enhanced with format conversion support.
        """
        button_id = str(temp_path_info["button_id"])
        if self.metadata.get(button_id, {}).get('read_only'):
            logger.warning(f"Finalizing recording blocked: Button {button_id} is read-only.")
            return

        temp_path = Path(temp_path_info["temp_path"])
        message_type = temp_path_info["message_type"]
        
        # Generate final filename
        if self.audio_format in ['alaw', 'ulaw']:
            final_name = temp_path.stem + f"_{self.audio_format}.wav"
        else:
            final_name = temp_path.name
            
        final_path = self.storage_dir / final_name
        
        # Convert audio format if needed
        if self.audio_format in ['alaw', 'ulaw']:
            success = self._convert_audio_format(temp_path, final_path, self.audio_format)
            if not success:
                logger.error(f"Audio conversion failed, using original format")
                shutil.move(temp_path, final_path)
        else:
            shutil.move(temp_path, final_path)
        
        logger.info(f"Finalized recording for button '{button_id}' to {final_path}")

        # Update occupied sets for legacy compatibility
        if message_type == "away_message":
            self.occupied_away_messages.add(button_id)
        elif message_type == "custom_message":
            self.occupied_custom_messages.add(button_id)

        # Update metadata
        self.metadata[button_id] = {
            "name": final_path.name,
            "duration": temp_path_info["duration"],
            "path": str(final_path),
            "timestamp": temp_path_info["timestamp"],
            "message_type": message_type,
            "audio_format": self.audio_format,
            "sample_rate": temp_path_info.get("sample_rate", self.sample_rate),
            "channels": temp_path_info.get("channels", self.channels),
            "read_only": False,
            "is_default": False
        }
        self._save_metadata()

    def _convert_audio_format(self, input_path: Path, output_path: Path, target_format: str) -> bool:
        """
        Convert audio format using FFmpeg. Legacy compatibility method.
        """
        if target_format == "alaw":
            codec_out = "pcm_alaw"
        elif target_format == "ulaw":
            codec_out = "pcm_mulaw"
        else:
            return False

        command = [
            "ffmpeg", "-y",  # overwrite output
            "-i", str(input_path),
            "-c:a", codec_out,
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(output_path)
        ]

        try:
            process = subprocess.run(command, capture_output=True, timeout=10, text=True)
            if process.returncode == 0:
                logger.info(f"Successfully converted {input_path} to {target_format}")
                return True
            else:
                logger.error(f"FFmpeg conversion failed: {process.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out")
            return False
        except FileNotFoundError:
            logger.error("FFmpeg not found. Install FFmpeg for audio format conversion.")
            return False

    def cleanup(self) -> None:
        """Cleanup resources and stop any running operations."""
        self._exit_flag = True
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=1.0)
        self._temp_dir_obj.cleanup()

    def discard_recording(self, button_id: Union[str, int]) -> None:
        """Remove temporary files for the given button ID."""
        button_id = str(button_id)
        for f in self.temp_dir.glob(f"{button_id}_*.wav"):
            f.unlink()

    def set_read_only(self, button_id: Union[str, int], read_only: bool = True) -> None:
        """Set read-only flag for a button."""
        button_id = str(button_id)
        if button_id not in self.metadata:
            return
        self.metadata[button_id]['read_only'] = read_only
        self._save_metadata()

    def get_recording_info(self, button_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Get recording information for a button."""
        return self.metadata.get(str(button_id))

    def list_all_recordings(self) -> Dict[str, Dict[str, Any]]:
        """Get all recording metadata."""
        return self.metadata

    def assign_default(self, button_id: Union[str, int], file_path: Union[str, Path]) -> None:
        """Assign a default audio file to a button."""
        button_id = str(button_id)
        if not Path(file_path).exists():
            logger.error(f"Cannot assign default: source file not found at {file_path}")
            return

        default_name = f"default_{button_id}.wav"
        default_path = self.storage_dir / default_name
        shutil.copy(file_path, default_path)

        duration = None
        try:
            with wave.open(str(default_path), 'rb') as wf:
                duration = round(wf.getnframes() / float(wf.getframerate()), 2)
        except wave.Error:
            logger.warning(f"Could not read duration from {default_path}. Duration set to None.")

        self.metadata[button_id] = {
            "name": default_name,
            "duration": duration,
            "path": str(default_path),
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "default",
            "audio_format": "wav",
            "read_only": True,
            "is_default": True
        }
        self._save_metadata()

    def restore_default(self, button_id: Union[str, int]) -> None:
        """Restore a button to its default audio file."""
        button_id = str(button_id)
        default_path = self.storage_dir / f"default_{button_id}.wav"
        if not default_path.exists():
            logger.warning(f"Cannot restore default for '{button_id}': default file not found.")
            return

        restored_path = self.storage_dir / f"{button_id}_restored_{int(time.time())}.wav"
        shutil.copy(default_path, restored_path)

        duration = None
        try:
            with wave.open(str(restored_path), 'rb') as wf:
                duration = round(wf.getnframes() / float(wf.getframerate()), 2)
        except wave.Error:
            logger.warning(f"Could not read duration from restored file {restored_path}. Duration set to None.")

        self.metadata[button_id] = {
            "name": restored_path.name,
            "duration": duration,
            "path": str(restored_path),
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "restored_default",
            "audio_format": "wav",
            "read_only": False,
            "is_default": False
        }
        self._save_metadata()

    def get_audio_device_info(self) -> Dict[str, Any]:
        """Get information about the current audio device."""
        return self.audio_backend.get_device_info()

    def update_json_backup(self, message_type: str = ""):
        """Legacy compatibility method for JSON backup updates."""
        logger.info("JSON backup updated via metadata save")
        self._save_metadata()

    @staticmethod
    def create_timestamp() -> str:
        """Create a timestamp string. Legacy compatibility method."""
        return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))